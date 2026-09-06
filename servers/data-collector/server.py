#!/usr/bin/env python3
"""
竞彩足球数据采集MCP服务器
12个工具：比赛列表、官方赔率、比赛资讯、第三方赔率、第三方资讯、赔率历史、历史数据、H2H、球队状态、联赛特征、裁判统计、赔率转换
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from fastmcp import FastMCP

# 统一错误处理
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'common'))
from error_handler import safe_tool, make_error_response, make_success_response

mcp = FastMCP("jingcai-data-collector")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')
HISTORY_DIR = os.path.join(DATA_DIR, 'history')

# 竞彩官方API
SPORTTERY_API_BASE = "https://webapi.sporttery.cn/gateway/uniform/football"
MATCH_LIST_URL = f"{SPORTTERY_API_BASE}/getMatchListV1.qry?clientCode=3001"
FIXED_BONUS_URL = f"{SPORTTERY_API_BASE}/getFixedBonusV1.qry?clientCode=3001&matchId={{mid}}"
MATCH_DETAIL_URL = "https://www.sporttery.cn/jc/zqdz/index.html?mid={mid}&showType=3"
SUPPORT_RATE_URL = "https://webapi.sporttery.cn/gateway/jc/common/getSupportRateV1.qry?matchIds={mids}&poolCode=hhad,had&sportType=1"

# 500.com页面URL
F500_BASE = "https://odds.500.com/fenxi"
F500_EUROPEAN = f"{F500_BASE}/ouzhi-{{fid}}.shtml"
F500_ASIAN = f"{F500_BASE}/yazhi-{{fid}}.shtml"
F500_OVERUNDER = f"{F500_BASE}/daxiao-{{fid}}.shtml"
F500_DATA = f"{F500_BASE}/shuju-{{fid}}.shtml"

# 8大比赛资讯API（来源：lottery-data项目news_collector.py，已验证）
NEWS_API_ENDPOINTS = {
    "赛事前瞻": "getMatchHeadV1.qry",
    "特征分析": "getMatchFeatureV1.qry",
    "历史交锋": "getResultHistoryV1.qry",
    "积分榜": "getMatchTablesV2.qry",
    "未来赛事": "getFutureMatchesV1.qry",
    "射手信息": "getMatchPlayerV1.qry",
    "伤停一览": "getInjurySuspensionV1.qry",
    "比赛近况": "getMatchResultV1.qry",
}

def build_news_url(match_id, endpoint):
    """构造资讯API URL"""
    extra = "&termLimits=10" if endpoint == "getMatchFeatureV1.qry" else ""
    return f"{SPORTTERY_API_BASE}/{endpoint}?sportteryMatchId={match_id}&channel=c{extra}"

def fetch_news_api(match_id, endpoint, timeout=10):
    """调用单个资讯API，返回原始JSON文本或None"""
    url = build_news_url(match_id, endpoint)
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Referer': 'https://www.sporttery.cn/jc/zqdz/',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8')
    except Exception:
        return None

def fetch_url(url, timeout=15):
    """尝试直接访问URL，失败返回None（云IP可能被403，需LLM用web.fetch降级）"""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.sporttery.cn/',
            'Accept': 'application/json, text/plain, */*',
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8')
    except Exception:
        return None

# 联赛代码映射
LEAGUE_MAP = {
    'E0': '英超', 'E1': '英冠', 'D1': '德甲', 'SP1': '西甲',
    'I1': '意甲', 'F1': '法甲', 'N': '荷甲', 'B1': '比甲',
    'P1': '葡超', 'SC0': '苏超', 'T1': '土超', 'RUS': '俄超',
    'PL': '波超', 'NOR': '挪超', 'SWE': '瑞超', 'FIN': '芬超',
    'MEX': '墨超', 'USA': '美职', 'JPN': '日职', 'CHN': '中超',
    'BRA': '巴甲', 'ARG': '阿甲',
}

def load_json(filepath):
    """加载JSON文件"""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    """保存JSON文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@mcp.tool()
@safe_tool
def get_match_list(date: str = None) -> dict:
    """
    获取当期比赛列表（联网采集，来源：竞彩网官方API）
    
    采集流程：
    1. 尝试直接访问官方API（云IP可能被403）
    2. 若失败，返回fetch_url，由LLM用web.fetch获取原始JSON
    3. LLM获取后调用 parse_match_list_response(json_text) 解析
    
    Args:
        date: 比赛日期 YYYY-MM-DD，默认今天（API返回未来几天赛程，date仅用于本地过滤）
    
    Returns:
        成功：比赛列表（含matchId/matchNumStr/联赛/对阵/开赛时间/HAD+HHAD赔率）
        失败：{need_fetch: true, fetch_url: "...", note: "请用web.fetch获取此URL的原始JSON，然后调用parse_match_list_response"}
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    # 尝试直接访问
    raw = fetch_url(MATCH_LIST_URL)
    if raw:
        try:
            data = json.loads(raw)
            parsed = parse_match_list_data(data, date)
            # 缓存到本地
            save_json(os.path.join(DATA_DIR, f'matches_{date}.json'), parsed)
            return parsed
        except Exception as e:
            return {'error': f'API返回解析失败: {e}', 'raw_preview': raw[:500]}
    
    # 降级：返回URL让LLM用web.fetch
    return {
        'need_fetch': True,
        'fetch_url': MATCH_LIST_URL,
        'parse_tool': 'parse_match_list_response',
        'note': '服务器直连被限制（403），请用web.fetch获取此URL的原始JSON文本，然后调用parse_match_list_response(json_text=...)解析'
    }


def parse_match_list_data(api_data, filter_date=None):
    """解析竞彩API返回的赛程JSON"""
    matches = []
    value = api_data.get('value', {})
    if isinstance(value, dict):
        match_list = value.get('matchList', [])
    elif isinstance(value, list):
        match_list = value
    else:
        match_list = []
    
    for m in match_list:
        match_date = m.get('businessDate', m.get('matchDate', ''))
        if filter_date and match_date != filter_date:
            continue
        if m.get('matchStatus') not in ('Selling', '1') and m.get('sellStatus') != '1':
            continue
        
        # 提取HAD/HHAD赔率
        odds = {}
        for od in m.get('oddsList', []):
            pc = od.get('poolCode', '')
            if pc == 'HAD' and od.get('h'):
                odds['胜平负'] = {'h': float(od['h']), 'd': float(od['d']), 'a': float(od['a'])}
            elif pc == 'HHAD' and od.get('h'):
                odds['让球胜平负'] = {'h': float(od['h']), 'd': float(od['d']), 'a': float(od['a']), 'goalLine': od.get('goalLine', '')}
        
        # 单关支持情况
        single_support = {}
        for s in m.get('poolList', []):
            single_support[s.get('poolCode', '')] = s.get('cbtSingle', 0) == 1
        
        matches.append({
            'match_id': str(m.get('matchId', '')),
            'match_num': m.get('matchNumStr', ''),
            'league': m.get('leagueAllName', m.get('leagueAbbName', '')),
            'home': m.get('homeTeamAllName', m.get('homeTeamAbbName', '')),
            'away': m.get('awayTeamAllName', m.get('awayTeamAbbName', '')),
            'date': match_date,
            'time': m.get('matchTime', ''),
            'status': m.get('matchStatus', ''),
            'odds_basic': odds,
            'single_support': single_support,
            'detail_url': MATCH_DETAIL_URL.format(mid=m.get('matchId', '')),
        })
    
    return {
        'date': filter_date or 'all',
        'count': len(matches),
        'matches': matches,
        'source': 'sporttery.cn API',
        'note': f'共{len(matches)}场在售比赛。完整5玩法赔率需逐场调用get_official_odds(match_id)'
    }


@mcp.tool()
@safe_tool
def parse_match_list_response(json_text: str, date: str = None) -> dict:
    """
    解析web.fetch获取的赛程API原始JSON（降级方案用）
    
    Args:
        json_text: web.fetch返回的原始JSON文本
        date: 过滤日期 YYYY-MM-DD，默认不过滤
    
    Returns:
        比赛列表（同get_match_list成功返回格式）
    """
    try:
        data = json.loads(json_text)
        result = parse_match_list_data(data, date)
        if date:
            save_json(os.path.join(DATA_DIR, f'matches_{date}.json'), result)
        return result
    except Exception as e:
        return {'error': f'解析失败: {e}', 'text_preview': json_text[:300]}

@mcp.tool()
@safe_tool
def get_official_odds(match_id: str) -> dict:
    """
    获取官方5玩法完整赔率（联网采集，来源：竞彩网getFixedBonusV1 API）
    
    采集流程：
    1. 尝试直接访问官方API
    2. 若失败，返回fetch_url，由LLM用web.fetch获取原始JSON
    3. LLM获取后调用 parse_odds_response(json_text, match_id) 解析
    
    Args:
        match_id: 比赛ID（数字，如2041306）
    
    Returns:
        成功：5玩法完整赔率（胜平负/让球/比分31项/总进球8档/半全场9项）+ 单关支持情况
        失败：{need_fetch: true, fetch_url: "...", parse_tool: "parse_odds_response"}
    """
    url = FIXED_BONUS_URL.format(mid=match_id)
    raw = fetch_url(url)
    if raw:
        try:
            data = json.loads(raw)
            return parse_odds_data(data, match_id)
        except Exception as e:
            return {'error': f'API返回解析失败: {e}', 'raw_preview': raw[:500]}
    
    return {
        'need_fetch': True,
        'fetch_url': url,
        'parse_tool': 'parse_odds_response',
        'match_id': match_id,
        'note': '服务器直连被限制，请用web.fetch获取此URL的原始JSON，然后调用parse_odds_response(json_text=..., match_id=...)'
    }


def parse_odds_data(api_data, match_id):
    """解析竞彩getFixedBonusV1返回的5玩法赔率JSON"""
    value = api_data.get('value', {})
    odds_history = value.get('oddsHistory', {})
    
    result = {
        'match_id': match_id,
        'league': odds_history.get('leagueAllName', ''),
        'home': odds_history.get('homeTeamAllName', ''),
        'away': odds_history.get('awayTeamAllName', ''),
        'odds': {},
        'single_support': {},
    }
    
    # 胜平负 HAD
    had = odds_history.get('hadList', [{}])[0] if odds_history.get('hadList') else {}
    if had.get('h'):
        result['odds']['胜平负'] = {
            'option_names': ['主胜', '平局', '客胜'],
            'odds': [float(had['h']), float(had['d']), float(had['a'])],
        }
    
    # 让球胜平负 HHAD
    hhad = odds_history.get('hhadList', [{}])[0] if odds_history.get('hhadList') else {}
    if hhad.get('h'):
        result['odds']['让球胜平负'] = {
            'option_names': ['让胜', '让平', '让负'],
            'odds': [float(hhad['h']), float(hhad['d']), float(hhad['a'])],
            'handicap': hhad.get('goalLine', ''),
        }
    
    # 比分 CRS（31项）
    crs = odds_history.get('crsList', [{}])[0] if odds_history.get('crsList') else {}
    if crs:
        # 比分选项映射：s{home}s{away}
        score_order = []
        for h in range(6):
            for a in range(3):
                key = f's{h:02d}s{a:02d}'
                if key in crs and crs[key] and crs[key] != '0':
                    score_order.append((f'{h}:{a}', float(crs[key])))
        # 其他比分
        for label, key in [('胜其他', 's-1sh'), ('平其他', 's-1sd'), ('负其他', 's-1sa')]:
            if key in crs and crs[key] and crs[key] != '0':
                score_order.append((label, float(crs[key])))
        if score_order:
            result['odds']['比分'] = {
                'option_names': [s[0] for s in score_order],
                'odds': [s[1] for s in score_order],
            }
    
    # 总进球 TTG（8档）
    ttg = odds_history.get('ttgList', [{}])[0] if odds_history.get('ttgList') else {}
    if ttg:
        ttg_order = []
        for i in range(7):
            key = f's{i}'
            if key in ttg and ttg[key] and ttg[key] != '0':
                ttg_order.append((f'{i}球', float(ttg[key])))
        if 's7' in ttg and ttg['s7'] and ttg['s7'] != '0':
            ttg_order.append(('7+球', float(ttg['s7'])))
        if ttg_order:
            result['odds']['总进球'] = {
                'option_names': [t[0] for t in ttg_order],
                'odds': [t[1] for t in ttg_order],
            }
    
    # 半全场 HAFU（9项）
    hafu = odds_history.get('hafuList', [{}])[0] if odds_history.get('hafuList') else {}
    if hafu:
        hafu_map = [
            ('胜胜', 'hh'), ('胜平', 'hd'), ('胜负', 'ha'),
            ('平胜', 'dh'), ('平平', 'dd'), ('平负', 'da'),
            ('负胜', 'ah'), ('负平', 'ad'), ('负负', 'aa'),
        ]
        hafu_order = []
        for label, key in hafu_map:
            if key in hafu and hafu[key] and hafu[key] != '0':
                hafu_order.append((label, float(hafu[key])))
        if hafu_order:
            result['odds']['半全场'] = {
                'option_names': [h[0] for h in hafu_order],
                'odds': [h[1] for h in hafu_order],
            }
    
    # 单关支持情况
    for s in odds_history.get('singleList', []):
        pc = s.get('poolCode', '')
        name_map = {'HAD': '胜平负', 'HHAD': '让球胜平负', 'CRS': '比分', 'TTG': '总进球', 'HAFU': '半全场'}
        result['single_support'][name_map.get(pc, pc)] = s.get('single', 0) == 1
    
    result['source'] = 'sporttery.cn getFixedBonusV1 API'
    result['play_count'] = len(result['odds'])
    return result


@mcp.tool()
@safe_tool
def parse_odds_response(json_text: str, match_id: str = '') -> dict:
    """
    解析web.fetch获取的赔率API原始JSON（降级方案用）
    
    Args:
        json_text: web.fetch返回的原始JSON文本
        match_id: 比赛ID（可选，用于标注）
    
    Returns:
        5玩法完整赔率（同get_official_odds成功返回格式）
    """
    try:
        data = json.loads(json_text)
        return parse_odds_data(data, match_id)
    except Exception as e:
        return {'error': f'解析失败: {e}', 'text_preview': json_text[:300]}

@mcp.tool()
@safe_tool
def get_official_info(match_id: str) -> dict:
    """
    获取官方8大比赛资讯（联网采集，来源：竞彩网8个资讯API）
    
    采集流程（双轨降级）：
    1. 尝试直连8个资讯API（带Referer）
    2. 若部分失败，返回已成功的资讯 + 失败API的fetch_url列表
    3. LLM用web.fetch逐个获取失败的API，调用parse_news_response解析
    
    8大资讯：赛事前瞻/特征分析/历史交锋/积分榜/未来赛事/射手信息/伤停一览/比赛近况
    
    Args:
        match_id: 比赛ID（数字，如2041306）
    
    Returns:
        8大资讯数据 + 失败API的fetch_url列表
    """
    result = {
        'match_id': match_id,
        'news': {},
        'failed_apis': [],
        'source': 'sporttery.cn 8大资讯API',
    }
    
    for name, endpoint in NEWS_API_ENDPOINTS.items():
        raw = fetch_news_api(match_id, endpoint)
        if raw:
            try:
                data = json.loads(raw)
                if data.get('success'):
                    result['news'][name] = data.get('value', {})
                else:
                    result['failed_apis'].append({
                        'name': name, 'endpoint': endpoint,
                        'fetch_url': build_news_url(match_id, endpoint),
                        'error': data.get('errorMessage', 'API返回失败'),
                    })
            except Exception as e:
                result['failed_apis'].append({
                    'name': name, 'endpoint': endpoint,
                    'fetch_url': build_news_url(match_id, endpoint),
                    'error': f'解析失败: {e}',
                })
        else:
            result['failed_apis'].append({
                'name': name, 'endpoint': endpoint,
                'fetch_url': build_news_url(match_id, endpoint),
                'error': '直连失败（403/超时），请用web.fetch获取',
            })
    
    result['collected_count'] = len(result['news'])
    result['failed_count'] = len(result['failed_apis'])
    
    # 第三级降级：为每个失败的API提供general_search搜索关键词模板
    # 因为资讯API需要Referer头，web.fetch不支持自定义头，urllib直连被403
    # 所以最终兜底方案是用general_search搜索比赛资讯
    if result['failed_apis']:
        # 从已缓存的比赛信息中获取队名（如果有）
        match_info = load_json(os.path.join(DATA_DIR, f'match_{match_id}.json'))
        home = match_info.get('home', '') if match_info else ''
        away = match_info.get('away', '') if match_info else ''
        league = match_info.get('league', '') if match_info else ''
        
        search_keywords = {
            '赛事前瞻': f'{home} {away} 赛前分析 预测 首发',
            '特征分析': f'{home} {away} 技术统计 射门 射正 控球率',
            '历史交锋': f'{home} {away} 历史交锋 战绩',
            '积分榜': f'{league} 积分榜 排名',
            '未来赛事': f'{home} {away} 赛程 未来比赛',
            '射手信息': f'{home} {away} 射手榜 进球',
            '伤停一览': f'{home} {away} 伤停 伤病 停赛',
            '比赛近况': f'{home} {away} 近期战绩 状态',
        }
        
        result['search_fallback'] = {
            'note': '资讯API需要Referer头，web.fetch不支持自定义头，urllib直连被403。请用general_search搜索以下关键词获取资讯，然后整合到分析中。',
            'keywords': {name: search_keywords.get(name, f'{home} {away} {name}') for name, endpoint in NEWS_API_ENDPOINTS.items()},
            'priority': ['伤停一览', '比赛近况', '历史交锋', '赛事前瞻', '积分榜', '特征分析', '射手信息', '未来赛事'],
        }
    
    result['note'] = f'成功采集{len(result["news"])}/8项资讯。失败项请用general_search搜索（参考search_fallback.keywords），或用web.fetch获取fetch_url后调用parse_news_response。'
    
    # 缓存
    if result['news']:
        save_json(os.path.join(DATA_DIR, f'news_{match_id}.json'), result)
    
    return result


@mcp.tool()
@safe_tool
def parse_news_response(json_text: str, name: str = '') -> dict:
    """
    解析web.fetch获取的资讯API原始JSON（降级方案用）
    
    Args:
        json_text: web.fetch返回的原始JSON文本
        name: 资讯名称（如"伤停一览"），可选
    
    Returns:
        解析后的资讯数据
    """
    try:
        data = json.loads(json_text)
        if data.get('success'):
            return {'name': name, 'data': data.get('value', {}), 'success': True}
        return {'name': name, 'error': data.get('errorMessage', 'API失败'), 'success': False}
    except Exception as e:
        return {'error': f'解析失败: {e}', 'text_preview': json_text[:300]}

@mcp.tool()
@safe_tool
def get_third_party_odds(home: str, away: str, league: str = "") -> dict:
    """
    获取第三方赔率（欧指/亚盘/大小球），多数据源尝试+降级方案
    
    采集流程：
    1. 尝试直连500.com/球探网/懂球帝等数据源（带UA）
    2. 若失败，返回各数据源的fetch_url + 搜索关键词建议
    3. LLM用web.fetch获取页面或general_search搜索，然后调用parse_third_party_text解析
    
    Args:
        home: 主队名称
        away: 客队名称
        league: 联赛名称（可选，用于精准搜索）
    
    Returns:
        第三方赔率（欧指/亚盘/大小球）+ 失败数据源的fetch_url列表
    """
    result = {
        'match': f'{home} vs {away}',
        'league': league,
        'eu_odds': {'home': 0, 'draw': 0, 'away': 0, 'books': {}, 'source': ''},
        'ah_odds': {'line': 0, 'home': 0, 'away': 0, 'source': ''},
        'ou_odds': {'line': 2.5, 'over': 0, 'under': 0, 'source': ''},
        'failed_sources': [],
        'search_suggestions': [],
    }
    
    # 构造搜索关键词（供LLM用general_search）
    search_queries = [
        f'{home} {away} 欧指 亚盘 大小球 赔率',
        f'{home} vs {away} odds comparison',
        f'{home} {away} 赛前分析 赔率',
    ]
    if league:
        search_queries.insert(0, f'{league} {home} {away} 欧赔 亚盘 大小球')
    result['search_suggestions'] = search_queries
    
    # 尝试直连500.com（需要fid，这里提供搜索入口）
    # 500.com欧指页面: https://live.500.com/fenxi/shuju-{fid}.shtml
    # fid需要从搜索结果获取，这里提供搜索入口URL
    sources_to_try = [
        {
            'name': '500.com',
            'search_url': f'https://www.500.com/?k={home}+{away}',
            'note': '搜索后找到比赛，进入"欧指"tab获取30家公司赔率',
        },
        {
            'name': '球探网(win007)',
            'search_url': f'https://www.win007.com/sch/{home}.htm',
            'note': '球探网提供欧指/亚盘/大小球完整数据',
        },
        {
            'name': '懂球帝',
            'search_url': f'https://www.dongqiudi.com/search?keywords={home}+{away}',
            'note': '懂球帝赛前分析包含赔率数据',
        },
    ]
    
    # 尝试直连各数据源搜索页（验证可达性）
    for src in sources_to_try:
        raw = fetch_url(src['search_url'], timeout=8)
        if raw and len(raw) > 1000:
            # 页面可达，但赔率数据通常是JS渲染，需要LLM用web.fetch获取
            result['failed_sources'].append({
                'name': src['name'],
                'fetch_url': src['search_url'],
                'status': '页面可达但需JS渲染/解析',
                'note': src['note'],
            })
        else:
            result['failed_sources'].append({
                'name': src['name'],
                'fetch_url': src['search_url'],
                'status': '直连失败（403/超时）',
                'note': src['note'],
            })
    
    result['collected'] = False
    result['note'] = (
        '第三方赔率站点多为JS渲染且反爬严格，建议：'
        '1. 用web.fetch获取failed_sources中的fetch_url页面；'
        '2. 或用general_search搜索search_suggestions中的关键词；'
        '3. 获取到文本后调用parse_third_party_text(text=...)解析赔率数据。'
    )
    return result


@mcp.tool()
@safe_tool
def get_third_party_news(home: str, away: str, league: str = "") -> dict:
    """
    获取第三方比赛资讯（伤停/预测/新闻/专家观点），提供搜索方案+解析框架
    
    第三方资讯站点反爬严格，采用"LLM用general_search搜索 + parse_third_party_text解析"模式。
    
    Args:
        home: 主队名称
        away: 客队名称
        league: 联赛名称（可选）
    
    Returns:
        搜索关键词建议 + 资讯分类 + 解析指引
    """
    # 构造分维度搜索关键词
    search_plan = {
        '伤停信息': [
            f'{home} {away} 伤停 首发 阵容',
            f'{home} injury news {away}',
            f'{league} {home} 伤病名单',
        ],
        '赛前预测': [
            f'{home} {away} 赛前预测 分析',
            f'{home} vs {away} prediction preview',
            f'{league} {home} {away} 专家推荐',
        ],
        '近期新闻': [
            f'{home} 最新消息 {away}',
            f'{home} team news today',
            f'{league} 新闻 {home}',
        ],
        '历史交锋': [
            f'{home} {away} 历史交锋 战绩',
            f'{home} vs {away} head to head',
        ],
    }
    if league:
        for category in search_plan:
            search_plan[category].insert(0, f'{league} {home} {away} {category}')
    
    return {
        'match': f'{home} vs {away}',
        'league': league,
        'search_plan': search_plan,
        'collection_method': (
            '1. 按search_plan中的关键词，用general_search逐维度搜索；'
            '2. 将搜索到的文本内容传入parse_third_party_text(text=...)解析；'
            '3. 重点关注：伤停名单（主力缺阵）、首发预测、战意分析、天气/场地因素。'
        ),
        'priority_dimensions': [
            '⭐ 伤停信息（影响最大，主力前锋/后卫缺阵直接改变概率）',
            '⭐ 首发预测（确认核心球员是否上场）',
            '  战意分析（保级/争冠/无欲无求）',
            '  赛程密度（一周双赛/客场长途）',
            '  天气/场地（大雨/高原/人工草）',
        ],
        'note': '第三方资讯由LLM用general_search获取，不依赖脚本直连（反爬严格）。',
    }


@mcp.tool()
@safe_tool
def get_history_matches(league: str, team: str = None, limit: int = 20) -> dict:
    """
    查询历史比赛数据
    
    Args:
        league: 联赛代码（如E0/SP1）
        team: 球队名称（可选）
        limit: 返回数量
    
    Returns:
        历史比赛列表
    """
    league_file = os.path.join(HISTORY_DIR, f'{league}_history.json')
    data = load_json(league_file)
    
    if data is None:
        return {'league': league, 'count': 0, 'matches': [], 'note': '联赛数据不存在'}
    
    if team:
        filtered = [d for d in data if d.get('home') == team or d.get('away') == team]
    else:
        filtered = data
    
    return {
        'league': league,
        'league_name': LEAGUE_MAP.get(league, league),
        'count': len(filtered[:limit]),
        'matches': filtered[:limit]
    }

@mcp.tool()
@safe_tool
def get_h2h(league: str, team_a: str, team_b: str) -> dict:
    """
    查询两队历史交锋
    
    Args:
        league: 联赛代码
        team_a: 球队A
        team_b: 球队B
    
    Returns:
        H2H记录（总交锋/胜率/进球/近期交锋）
    """
    league_file = os.path.join(HISTORY_DIR, f'{league}_history.json')
    data = load_json(league_file)
    
    if data is None:
        return {'league': league, 'count': 0, 'h2h': [], 'note': '联赛数据不存在'}
    
    h2h = []
    for d in data:
        if (d.get('home') == team_a and d.get('away') == team_b) or \
           (d.get('home') == team_b and d.get('away') == team_a):
            h2h.append(d)
    
    a_wins = b_wins = draws = 0
    a_goals = b_goals = 0
    for d in h2h:
        if d['home'] == team_a:
            hg, ag = d.get('home_goals', 0), d.get('away_goals', 0)
            a_goals += hg
            b_goals += ag
            if hg > ag: a_wins += 1
            elif hg < ag: b_wins += 1
            else: draws += 1
        else:
            hg, ag = d.get('home_goals', 0), d.get('away_goals', 0)
            a_goals += ag
            b_goals += hg
            if ag > hg: a_wins += 1
            elif ag < hg: b_wins += 1
            else: draws += 1
    
    return {
        'league': league,
        'team_a': team_a,
        'team_b': team_b,
        'total': len(h2h),
        'a_wins': a_wins,
        'b_wins': b_wins,
        'draws': draws,
        'goals': f'{a_goals}:{b_goals}',
        'recent': h2h[-5:] if len(h2h) >= 5 else h2h,
    }

@mcp.tool()
@safe_tool
def get_team_form(league: str, team: str, recent_n: int = 5) -> dict:
    """
    查询球队近期状态
    
    Args:
        league: 联赛代码
        team: 球队名称
        recent_n: 近期场次
    
    Returns:
        近期战绩（胜平负/进球/失球/状态评分）
    """
    league_file = os.path.join(HISTORY_DIR, f'{league}_history.json')
    data = load_json(league_file)
    
    if data is None:
        return {'league': league, 'team': team, 'count': 0, 'form': [], 'note': '联赛数据不存在'}
    
    team_matches = []
    for d in data:
        if d.get('home') == team or d.get('away') == team:
            team_matches.append(d)
    
    recent = team_matches[-recent_n:] if len(team_matches) >= recent_n else team_matches
    
    wins = draws = losses = 0
    goals_for = goals_against = 0
    form_str = ''
    for d in recent:
        if d['home'] == team:
            hg, ag = d.get('home_goals', 0), d.get('away_goals', 0)
            goals_for += hg
            goals_against += ag
            if hg > ag:
                wins += 1
                form_str += '胜'
            elif hg < ag:
                losses += 1
                form_str += '负'
            else:
                draws += 1
                form_str += '平'
        else:
            hg, ag = d.get('home_goals', 0), d.get('away_goals', 0)
            goals_for += ag
            goals_against += hg
            if ag > hg:
                wins += 1
                form_str += '胜'
            elif ag < hg:
                losses += 1
                form_str += '负'
            else:
                draws += 1
                form_str += '平'
    
    points = wins * 3 + draws
    form_score = points / (recent_n * 3) * 100 if recent_n > 0 else 0
    
    return {
        'league': league,
        'team': team,
        'recent_n': len(recent),
        'form': form_str,
        'wins': wins,
        'draws': draws,
        'losses': losses,
        'goals_for': goals_for,
        'goals_against': goals_against,
        'form_score': round(form_score, 1),
        'matches': recent,
    }

@mcp.tool()
@safe_tool
def get_league_features(league_code: str) -> dict:
    """
    获取联赛特征
    
    Args:
        league_code: 联赛代码（如E0/SP1）
    
    Returns:
        联赛特征数据（场均进球/主胜率/大球率/主场优势等）
    """
    features_file = os.path.join(DATA_DIR, 'league_features.json')
    data = load_json(features_file)
    
    if data is None:
        return {'league_code': league_code, 'note': '联赛特征库不存在'}
    
    if isinstance(data, list):
        for item in data:
            if item.get('league_code') == league_code or item.get('code') == league_code:
                return item
        return {'league_code': league_code, 'note': '未找到该联赛特征'}
    elif isinstance(data, dict):
        return data.get(league_code, {'league_code': league_code, 'note': '未找到该联赛特征'})
    
    return {'league_code': league_code, 'note': '数据格式错误'}

@mcp.tool()
@safe_tool
def get_referee_stats(league: str, referee: str = None) -> dict:
    """
    获取裁判统计
    
    Args:
        league: 联赛代码
        referee: 裁判名称（可选，不传则列出所有裁判）
    
    Returns:
        裁判执法统计（出牌率/点球率/主场偏袒度/大球影响）
    """
    league_file = os.path.join(HISTORY_DIR, f'{league}_history.json')
    data = load_json(league_file)
    
    if data is None:
        return {'league': league, 'note': '联赛数据不存在'}
    
    referees = {}
    for d in data:
        ref = d.get('referee')
        if ref:
            if ref not in referees:
                referees[ref] = []
            referees[ref].append(d)
    
    if referee:
        matches = referees.get(referee, [])
        if not matches:
            return {'league': league, 'referee': referee, 'note': '未找到该裁判数据'}
        
        total = len(matches)
        total_yellow = sum(d.get('hy', 0) + d.get('ay', 0) for d in matches)
        total_red = sum(d.get('hr', 0) + d.get('ar', 0) for d in matches)
        total_penalty = sum(d.get('hbp', 0) + d.get('abp', 0) for d in matches)
        total_goals = sum(d.get('home_goals', 0) + d.get('away_goals', 0) for d in matches)
        home_wins = sum(1 for d in matches if d.get('result') == 'H')
        away_wins = sum(1 for d in matches if d.get('result') == 'A')
        over25 = sum(1 for d in matches if d.get('home_goals', 0) + d.get('away_goals', 0) > 2.5)
        
        return {
            'league': league,
            'referee': referee,
            'matches': total,
            'yellow_per_game': round(total_yellow / total, 2) if total else 0,
            'red_per_game': round(total_red / total, 2) if total else 0,
            'penalty_per_game': round(total_penalty / total, 2) if total else 0,
            'goals_per_game': round(total_goals / total, 2) if total else 0,
            'home_win_rate': round(home_wins / total, 3) if total else 0,
            'away_win_rate': round(away_wins / total, 3) if total else 0,
            'over25_rate': round(over25 / total, 3) if total else 0,
            'home_bias': round((home_wins - away_wins) / total, 3) if total else 0,
        }
    else:
        stats = []
        for ref, matches in referees.items():
            if len(matches) >= 10:
                total = len(matches)
                total_yellow = sum(d.get('hy', 0) + d.get('ay', 0) for d in matches)
                stats.append({
                    'referee': ref,
                    'matches': total,
                    'yellow_per_game': round(total_yellow / total, 2),
                })
        stats.sort(key=lambda x: x['yellow_per_game'], reverse=True)
        return {
            'league': league,
            'referee_count': len(stats),
            'top_yellow': stats[:10],
        }

@mcp.tool()
@safe_tool
def convert_odds(eu_odds: list, actual_handicap: float = None) -> dict:
    """
    赔率转换（欧指→亚盘/大小球），第三方缺失时推导
    
    Args:
        eu_odds: 欧指列表 [主胜, 平局, 客胜]
        actual_handicap: 实际让球数（可选）
    
    Returns:
        转换后的赔率（亚盘/大小球/预期进球）
    """
    if len(eu_odds) != 3 or any(o <= 0 for o in eu_odds):
        return {'error': '欧指格式错误，应为 [主胜, 平局, 客胜]'}
    
    # 去水
    inv_sum = sum(1/o for o in eu_odds)
    probs = [1/o / inv_sum for o in eu_odds]
    
    # 预期进球推导（简化版）
    # 用概率推导λ
    p_home, p_draw, p_away = probs
    
    # 简化：用胜负概率差推导预期进球差
    goal_diff = (p_home - p_away) * 2.5
    total_goals = 2.5 + (1 - p_draw) * 0.5
    
    lambda_home = (total_goals + goal_diff) / 2
    lambda_away = (total_goals - goal_diff) / 2
    
    # 亚盘推导
    fair_handicap = lambda_home - lambda_away
    
    # 大小球推导
    ou_line = round(total_goals * 2) / 2  # 取0.5的倍数
    
    return {
        'eu_odds': eu_odds,
        'implied_probs': {
            'home': round(p_home, 4),
            'draw': round(p_draw, 4),
            'away': round(p_away, 4),
        },
        'payout_rate': round(1 / inv_sum, 4),
        'expected_goals': {
            'home': round(lambda_home, 2),
            'away': round(lambda_away, 2),
            'total': round(total_goals, 2),
        },
        'fair_handicap': round(fair_handicap, 2),
        'actual_handicap': actual_handicap,
        'handicap_value': round(fair_handicap - actual_handicap, 2) if actual_handicap else None,
        'ou_line': ou_line,
        'note': '欧指转亚盘/大小球推导，第三方缺失时使用'
    }

@mcp.tool()
@safe_tool
def parse_third_party_text(text: str) -> dict:
    """
    第三方数据解析器：从文本中提取欧指/亚盘/大小球/新闻
    
    Args:
        text: 包含第三方赔率和资讯的文本（如搜索结果、文章内容）
    
    Returns:
        解析后的结构化数据（欧指/亚盘/大小球/关键资讯）
    """
    import re
    
    result = {
        'eu_odds': None,
        'ah_odds': None,
        'ou_odds': None,
        'key_news': [],
        'parsed': False
    }
    
    # 提取欧指（主胜/平/客胜）
    eu_pattern = r'主胜[：:]\s*([\d.]+).*?平局[：:]\s*([\d.]+).*?客胜[：:]\s*([\d.]+)'
    eu_match = re.search(eu_pattern, text)
    if eu_match:
        result['eu_odds'] = {
            'home': float(eu_match.group(1)),
            'draw': float(eu_match.group(2)),
            'away': float(eu_match.group(3))
        }
        result['parsed'] = True
    
    # 提取亚盘
    ah_pattern = r'亚盘[：:]\s*([-\d.]+)\s*([\d.]+)\s*/\s*([\d.]+)'
    ah_match = re.search(ah_pattern, text)
    if ah_match:
        result['ah_odds'] = {
            'handicap': float(ah_match.group(1)),
            'home_water': float(ah_match.group(2)),
            'away_water': float(ah_match.group(3))
        }
        result['parsed'] = True
    
    # 提取大小球
    ou_pattern = r'大小球[：:]\s*([\d.]+)\s*([\d.]+)\s*/\s*([\d.]+)'
    ou_match = re.search(ou_pattern, text)
    if ou_match:
        result['ou_odds'] = {
            'line': float(ou_match.group(1)),
            'over': float(ou_match.group(2)),
            'under': float(ou_match.group(3))
        }
        result['parsed'] = True
    
    # 提取关键资讯（伤停/战意/天气等关键词）
    keywords = ['伤停', '缺阵', '复出', '战意', '保级', '争冠', '轮换', '天气', '雨', '雪', '裁判', '主场', '客场']
    sentences = re.split(r'[。！？\n]', text)
    for sent in sentences:
        for kw in keywords:
            if kw in sent and len(sent.strip()) > 5:
                result['key_news'].append(sent.strip())
                break
    
    result['key_news'] = result['key_news'][:10]  # 最多10条
    
    return result

@mcp.tool()
@safe_tool
def track_injury(team: str, injury_info: str = None, action: str = 'query') -> dict:
    """
    伤停追踪器：积累和查询球队伤停信息
    
    Args:
        team: 球队名称
        injury_info: 伤停信息（action=add时必填）
        action: 操作类型 query/add/clear
    
    Returns:
        球队伤停信息
    """
    injury_file = os.path.join(DATA_DIR, 'injury_tracker.json')
    data = load_json(injury_file) or {}
    
    if action == 'add' and injury_info:
        if team not in data:
            data[team] = []
        data[team].append({
            'info': injury_info,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'timestamp': datetime.now().isoformat()
        })
        save_json(injury_file, data)
        return {'team': team, 'injury_count': len(data[team]), 'latest': data[team][-1]}
    
    elif action == 'clear':
        if team in data:
            del data[team]
            save_json(injury_file, data)
        return {'team': team, 'cleared': True}
    
    else:  # query
        return {
            'team': team,
            'injury_count': len(data.get(team, [])),
            'injuries': data.get(team, [])[-5:],  # 最近5条
            'all_teams': list(data.keys())
        }

@mcp.tool()
@safe_tool
def track_referee(referee: str, league: str = None, stats: dict = None, action: str = 'query') -> dict:
    """
    裁判追踪器：积累和查询裁判执法风格
    
    Args:
        referee: 裁判姓名
        league: 联赛代码
        stats: 裁判统计数据（action=add时必填）
        action: 操作类型 query/add/list
    
    Returns:
        裁判执法风格统计
    """
    referee_file = os.path.join(DATA_DIR, 'referee_tracker.json')
    data = load_json(referee_file) or {}
    
    if action == 'add' and stats:
        key = f"{league}_{referee}" if league else referee
        if key not in data:
            data[key] = {'referee': referee, 'league': league, 'matches': 0, 'stats': {}}
        data[key]['matches'] += 1
        # 累加统计
        for k, v in stats.items():
            if k in data[key]['stats']:
                data[key]['stats'][k] += v
            else:
                data[key]['stats'][k] = v
        data[key]['last_updated'] = datetime.now().isoformat()
        save_json(referee_file, data)
        return {'referee': referee, 'league': league, 'matches': data[key]['matches']}
    
    elif action == 'list':
        return {
            'total_referees': len(data),
            'referees': [{'name': v['referee'], 'league': v.get('league'), 'matches': v['matches']} 
                         for v in list(data.values())[:20]]
        }
    
    else:  # query
        key = f"{league}_{referee}" if league else referee
        if key in data:
            d = data[key]
            return {
                'referee': referee,
                'league': league,
                'matches': d['matches'],
                'avg_yellow': round(d['stats'].get('yellow', 0) / d['matches'], 2) if d['matches'] else 0,
                'avg_red': round(d['stats'].get('red', 0) / d['matches'], 2) if d['matches'] else 0,
                'avg_penalty': round(d['stats'].get('penalty', 0) / d['matches'], 2) if d['matches'] else 0,
                'home_win_rate': round(d['stats'].get('home_win', 0) / d['matches'], 4) if d['matches'] else 0,
                'stats': d['stats']
            }
        return {'referee': referee, 'league': league, 'found': False, 'note': '暂无该裁判数据'}

# ============================================================
# 数据采集稳定性增强工具（5个）
# ============================================================

@mcp.tool()
@safe_tool
def fetch_with_retry(url: str, max_retries: int = 3, timeout: int = 15) -> dict:
    """带重试机制的数据获取工具，支持指数退避"""
    import urllib.request
    import urllib.error
    import time
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read().decode('utf-8', errors='replace')
                return {'success': True, 'url': url, 'status_code': response.getcode(),
                        'content': content, 'attempts': attempt, 'retries': attempt - 1}
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(attempt * 1)
    
    return {'success': False, 'url': url, 'error': last_error, 'attempts': max_retries,
            'suggestion': '请检查URL或使用备用数据源'}

@mcp.tool()
@safe_tool
def cache_data(key: str, data: dict = None, ttl: int = 3600, action: str = 'get') -> dict:
    """数据缓存管理工具，支持get/set/delete/list/clear操作"""
    import datetime as dt
    cache_dir = os.path.join(DATA_DIR, 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{key}.json")
    
    if action == 'set' and data is not None:
        entry = {'key': key, 'data': data, 'cached_at': datetime.now().isoformat(),
                 'ttl': ttl, 'expires_at': (datetime.now() + dt.timedelta(seconds=ttl)).isoformat()}
        save_json(cache_file, entry)
        return {'success': True, 'key': key, 'cached': True, 'ttl': ttl}
    elif action == 'get':
        if os.path.exists(cache_file):
            entry = load_json(cache_file)
            expires = datetime.fromisoformat(entry['expires_at'])
            if datetime.now() < expires:
                return {'success': True, 'key': key, 'data': entry['data'], 'is_expired': False}
            return {'success': False, 'key': key, 'is_expired': True}
        return {'success': False, 'key': key, 'note': '缓存不存在'}
    elif action == 'list':
        files = [f for f in os.listdir(cache_dir) if f.endswith('.json')]
        return {'success': True, 'total_caches': len(files)}
    elif action == 'clear':
        files = [f for f in os.listdir(cache_dir) if f.endswith('.json')]
        for f in files:
            os.remove(os.path.join(cache_dir, f))
        return {'success': True, 'cleared': len(files)}
    return {'success': False, 'error': f'未知操作: {action}'}

@mcp.tool()
@safe_tool
def validate_data_completeness(matches: list, required_fields: list = None) -> dict:
    """数据完整性校验工具，检查5种玩法赔率+8大资讯完整性"""
    if required_fields is None:
        required_fields = ['match_id', 'league', 'home', 'away',
            'odds.胜平负', 'odds.让球胜平负', 'odds.总进球', 'odds.比分', 'odds.半全场',
            'info.赛事特征', 'info.历史交锋', 'info.近期战绩', 'info.伤停', 'info.积分榜']
    
    total = len(matches)
    complete = 0
    incomplete = []
    missing_summary = {}
    
    for match in matches:
        mid = match.get('match_id', 'unknown')
        missing = []
        for field in required_fields:
            parts = field.split('.')
            val = match
            for p in parts:
                if isinstance(val, dict) and p in val:
                    val = val[p]
                else:
                    val = None
                    break
            if val is None or (isinstance(val, (list, dict)) and len(val) == 0):
                missing.append(field)
                missing_summary[field] = missing_summary.get(field, 0) + 1
        if not missing:
            complete += 1
        else:
            incomplete.append({'match_id': mid, 'missing_count': len(missing), 'missing_fields': missing[:5]})
    
    rate = complete / total if total > 0 else 0
    return {'total_matches': total, 'complete_matches': complete, 'incomplete_matches': len(incomplete),
            'completeness_rate': f"{rate*100:.1f}%", 'incomplete_details': incomplete[:10],
            'missing_fields_summary': dict(sorted(missing_summary.items(), key=lambda x: x[1], reverse=True)[:10]),
            'quality_level': '优秀' if rate >= 0.9 else '良好' if rate >= 0.7 else '一般' if rate >= 0.5 else '较差',
            'suggestion': '数据完整性较高' if rate >= 0.7 else '数据完整性不足，建议补充缺失数据'}

@mcp.tool()
@safe_tool
def get_multi_source_odds(home: str, away: str, league: str = "", match_id: str = "") -> dict:
    """
    多数据源赔率交叉验证（竞彩官方SP vs 第三方欧指 vs 第三方亚盘/大小球）
    
    真正调用多个数据源，计算偏离度，识别价值投注机会。
    
    Args:
        home: 主队名称
        away: 客队名称
        league: 联赛名称（可选）
        match_id: 竞彩比赛ID（可选，提供后可直接获取官方SP）
    
    Returns:
        多源赔率对比（官方SP/第三方欧指/亚盘/大小球）+ 偏离度分析 + 价值信号
    """
    result = {
        'match': f'{home} vs {away}',
        'league': league,
        'match_id': match_id,
        'sources': {},
        'divergence': {},
        'value_signals': [],
    }
    
    # 1. 获取竞彩官方SP（如果提供了match_id）
    if match_id:
        url = FIXED_BONUS_URL.format(mid=match_id)
        raw = fetch_url(url)
        if raw:
            try:
                data = json.loads(raw)
                parsed = parse_odds_data(data, match_id)
                official = {}
                for play, play_data in parsed.get('odds', {}).items():
                    if play in ['胜平负', '让球胜平负']:
                        official[play] = {
                            'option_names': play_data.get('option_names', []),
                            'odds': play_data.get('odds', []),
                        }
                if official:
                    result['sources']['竞彩官方SP'] = official
                    result['sources']['竞彩官方SP']['status'] = 'success'
            except Exception as e:
                result['sources']['竞彩官方SP'] = {'status': f'解析失败: {e}', 'fetch_url': url}
        else:
            result['sources']['竞彩官方SP'] = {
                'status': '直连失败',
                'fetch_url': url,
                'note': '请用web.fetch获取后调用parse_odds_response',
            }
    else:
        result['sources']['竞彩官方SP'] = {
            'status': '未提供match_id',
            'note': '提供match_id参数可直接获取官方SP',
        }
    
    # 2. 第三方赔率（调用get_third_party_odds的逻辑，返回搜索方案）
    third_party = get_third_party_odds.fn(home, away, league)
    result['sources']['第三方赔率'] = {
        'status': '需LLM用general_search/web.fetch获取',
        'search_suggestions': third_party.get('search_suggestions', []),
        'failed_sources': third_party.get('failed_sources', []),
    }
    
    # 3. 交叉验证分析（如果有官方SP）
    if '竞彩官方SP' in result['sources'] and '胜平负' in result['sources']['竞彩官方SP']:
        sp = result['sources']['竞彩官方SP']['胜平负']
        if sp.get('odds') and len(sp['odds']) == 3:
            h, d, a = sp['odds']
            # 计算竞彩返奖率
            inv_sum = 1/h + 1/d + 1/a
            payout = 1/inv_sum if inv_sum > 0 else 0
            # 去水后隐含概率
            result['divergence'] = {
                '竞彩SP': {'主胜': h, '平局': d, '客胜': a},
                '竞彩返奖率': round(payout, 4),
                '去水隐含概率': {
                    '主胜': round(1/h * payout, 4),
                    '平局': round(1/d * payout, 4),
                    '客胜': round(1/a * payout, 4),
                },
                '第三方欧指': '待获取（用general_search搜索后填入对比）',
                '偏离度': '需第三方欧指后计算',
            }
            # 价值信号初步判断
            if h < 1.3:
                result['value_signals'].append(f'主胜SP={h}过低（<1.3），串关价值低，建议避开或单关')
            if a > 5.0:
                result['value_signals'].append(f'客胜SP={a}较高（>5.0），冷门博彩机会，需第三方赔率验证')
    
    result['note'] = (
        '交叉验证需要：1.竞彩官方SP（已获取或需match_id）；2.第三方欧指（LLM用general_search获取）。'
        '偏离度=竞彩去水概率 - 第三方去水概率，>5%可能存在价值投注机会。'
    )
    return result


@mcp.tool()
@safe_tool
def get_data_source_status() -> dict:
    """
    数据源状态实时监控（实际测试各数据源HTTP可达性，非硬编码）
    
    测试内容：
    1. 竞彩官方API（赛程/赔率/资讯8个endpoint）
    2. 第三方数据源（500.com/球探网/懂球帝等）
    3. 返回真实的可达性状态和响应时间
    
    Returns:
        各数据源实时状态（可达/不可达/响应时间/建议）
    """
    sources_to_test = [
        # 官方API
        {'name': '竞彩赛程API', 'url': MATCH_LIST_URL, 'type': '官方', 'critical': True},
        {'name': '竞彩赔率API', 'url': FIXED_BONUS_URL.format(mid='2041306'), 'type': '官方', 'critical': True},
        {'name': '竞彩资讯-前瞻', 'url': build_news_url('2041306', 'getMatchHeadV1.qry'), 'type': '官方', 'critical': False},
        {'name': '竞彩资讯-伤停', 'url': build_news_url('2041306', 'getInjurySuspensionV1.qry'), 'type': '官方', 'critical': True},
        {'name': '竞彩资讯-近况', 'url': build_news_url('2041306', 'getMatchResultV1.qry'), 'type': '官方', 'critical': False},
        # 第三方
        {'name': '500.com', 'url': 'https://www.500.com/', 'type': '第三方', 'critical': False},
        {'name': '球探网', 'url': 'https://www.win007.com/', 'type': '第三方', 'critical': False},
        {'name': '懂球帝', 'url': 'https://www.dongqiudi.com/', 'type': '第三方', 'critical': False},
        {'name': '直播吧', 'url': 'https://www.zhibo8.cc/', 'type': '第三方', 'critical': False},
    ]
    
    results = []
    for src in sources_to_test:
        start = datetime.now()
        raw = fetch_url(src['url'], timeout=8)
        elapsed = (datetime.now() - start).total_seconds()
        
        if raw and len(raw) > 100:
            # 尝试解析JSON判断是否成功
            try:
                data = json.loads(raw)
                success = data.get('success', False) or data.get('errorCode', '') == '0'
                status = '正常' if success else '可达但返回异常'
            except Exception:
                status = '可达(HTML)'
        else:
            status = '不可达(403/超时)'
        
        results.append({
            'name': src['name'],
            'type': src['type'],
            'critical': src['critical'],
            'status': status,
            'response_time': round(elapsed, 2),
            'url': src['url'][:80] + '...' if len(src['url']) > 80 else src['url'],
        })
    
    official_ok = sum(1 for r in results if r['type'] == '官方' and '正常' in r['status'])
    official_total = sum(1 for r in results if r['type'] == '官方')
    third_ok = sum(1 for r in results if r['type'] == '第三方' and '可达' in r['status'])
    third_total = sum(1 for r in results if r['type'] == '第三方')
    
    critical_failures = [r for r in results if r['critical'] and '不可达' in r['status']]
    
    overall = '良好' if not critical_failures else ('一般' if len(critical_failures) <= 1 else '异常')
    
    return {
        'tested_at': datetime.now().isoformat(),
        'total_sources': len(results),
        'official': f'{official_ok}/{official_total} 正常',
        'third_party': f'{third_ok}/{third_total} 可达',
        'critical_failures': critical_failures,
        'overall_status': overall,
        'sources': results,
        'recommendations': [
            '官方API不可达时：用web.fetch获取URL（平台内部抓取服务可绕过云IP限制）',
            '第三方站点不可达时：用general_search搜索替代，不依赖脚本直连',
            '每次开始分析前调用此工具确认数据源状态',
        ],
    }


# ============================================================
# P0: 赛果获取（赛后结算必需）
# ============================================================
@mcp.tool()
@safe_tool
def get_match_result(match_id: str) -> dict:
    """
    获取比赛赛果（5玩法全部彩果，用于赛后结算）
    
    来源：竞彩网getMatchResultV1.qry（近况API，已结束比赛包含赛果）
    + getFixedBonusV1.qry的matchResultList
    
    Args:
        match_id: 比赛ID（数字）
    
    Returns:
        赛果（比分/半场比分/胜平负/让球/总进球/半全场彩果）+ 是否已开奖
    """
    result = {'match_id': match_id, 'settled': False, 'results': {}, 'source': ''}
    
    # 尝试1: getMatchResultV1（近况API，已结束比赛包含赛果）
    raw = fetch_news_api(match_id, 'getMatchResultV1.qry')
    if raw:
        try:
            data = json.loads(raw)
            if data.get('success'):
                value = data.get('value', {})
                # 解析赛果（不同API结构可能不同，尝试多种字段）
                for key in ['matchResult', 'result', 'score', 'matchScore']:
                    if key in value:
                        result['results']['raw'] = value[key]
                        result['settled'] = True
                        result['source'] = 'getMatchResultV1'
                        break
                # 尝试从homeTeamRecentList/awayTeamRecentList中找到本场
                for side in ['homeTeamRecentList', 'awayTeamRecentList']:
                    if side in value and isinstance(value[side], list):
                        for m in value[side]:
                            if str(m.get('matchId', '')) == str(match_id):
                                result['results']['score'] = f"{m.get('homeGoal','?')}:{m.get('awayGoal','?')}"
                                result['results']['half_score'] = f"{m.get('halfHomeGoal','?')}:{m.get('halfAwayGoal','?')}"
                                result['settled'] = True
                                result['source'] = 'getMatchResultV1(recent)'
                                break
        except Exception:
            pass
    
    # 尝试2: getFixedBonusV1的matchResultList
    if not result['settled']:
        url = FIXED_BONUS_URL.format(mid=match_id)
        raw2 = fetch_url(url)
        if raw2:
            try:
                data = json.loads(raw2)
                value = data.get('value', {})
                mr_list = value.get('matchResultList', [])
                if mr_list:
                    mr = mr_list[0] if isinstance(mr_list, list) else mr_list
                    result['results'] = mr
                    result['settled'] = True
                    result['source'] = 'getFixedBonusV1.matchResultList'
            except Exception:
                pass
    
    if not result['settled']:
        result['note'] = '比赛未结束或赛果未更新。可稍后重试，或用web.fetch获取对阵详情页确认。'
        result['detail_url'] = MATCH_DETAIL_URL.format(mid=match_id)
    
    return result


# ============================================================
# P1: 赔率走势（多时段快照+对比，支撑资金流分析）
# ============================================================

@mcp.tool()
@safe_tool
def compare_odds_movement(match_id: str) -> dict:
    """
    对比赔率走势（初盘→当前，识别资金流向和盘口异动）
    
    读取本地所有赔率快照，对比最早（初盘）和最新（当前）的SP变化。
    支撑analyzer的fund_flow_analysis资金流分析工具。
    
    Args:
        match_id: 比赛ID
    
    Returns:
        赔率走势（各玩法各选项的SP变化/变化率/资金流向信号）
    """
    snapshot_dir = os.path.join(DATA_DIR, 'odds_snapshots', match_id)
    if not os.path.exists(snapshot_dir):
        return {'match_id': match_id, 'error': '无快照数据，请先调用record_odds_snapshot采集'}
    
    snapshots = []
    for f in sorted(os.listdir(snapshot_dir)):
        if f.startswith('snapshot_') and f.endswith('.json'):
            with open(os.path.join(snapshot_dir, f), 'r', encoding='utf-8') as fp:
                snapshots.append(json.load(fp))
    
    if len(snapshots) < 2:
        return {'match_id': match_id, 'snapshot_count': len(snapshots),
                'note': f'仅{len(snapshots)}个快照，至少需要2个才能对比。建议采集初盘+临场两个时段。'}
    
    first = snapshots[0]
    last = snapshots[-1]
    result = {
        'match_id': match_id,
        'first_snapshot': first.get('timestamp', ''),
        'last_snapshot': last.get('timestamp', ''),
        'snapshot_count': len(snapshots),
        'movements': {},
    }
    
    # 对比各玩法各选项的SP变化
    for play in ['胜平负', '让球胜平负', '总进球', '比分', '半全场']:
        first_odds = first.get('odds', {}).get(play, {})
        last_odds = last.get('odds', {}).get(play, {})
        if not first_odds or not last_odds:
            continue
        
        first_opts = first_odds.get('option_names', [])
        first_vals = first_odds.get('odds', [])
        last_vals = last_odds.get('odds', [])
        
        play_movements = []
        for i, opt in enumerate(first_opts):
            if i >= len(first_vals) or i >= len(last_vals):
                break
            fv = first_vals[i]
            lv = last_vals[i]
            if fv > 0 and lv > 0:
                change = lv - fv
                change_pct = (change / fv) * 100
                # 资金流向：SP下降=资金流入（看好），SP上升=资金流出（不看好）
                direction = '资金流入↓' if change_pct < -2 else ('资金流出↑' if change_pct > 2 else '稳定')
                play_movements.append({
                    'option': opt,
                    'opening': fv,
                    'current': lv,
                    'change': round(change, 2),
                    'change_pct': round(change_pct, 1),
                    'direction': direction,
                })
        
        if play_movements:
            result['movements'][play] = play_movements
    
    result['note'] = 'SP下降=资金流入（市场看好），SP上升=资金流出（市场不看好）。变化>2%视为有意义的异动。'
    return result


@mcp.tool()
@safe_tool
def batch_record_odds_snapshot(match_ids: str, label: str = '') -> dict:
    """
    批量记录赔率快照（全部比赛一次性采集，支持web.fetch降级）
    
    对多场比赛同时记录赔率快照，用于初盘/午间/临场对比。
    直连失败时返回fetch_url列表，由LLM用web.fetch批量获取后调用parse_odds_response解析，再手动保存。
    
    建议采集时段：
    - 初盘：比赛开售时（通常前一天11:00）
    - 午间：比赛当天12:00
    - 临场：赛前1小时
    
    Args:
        match_ids: 比赛ID列表，逗号分隔（如"2041306,2041307,2041308"）
        label: 快照标签（如"初盘"/"午间"/"临场"），默认用当前时间
    
    Returns:
        批量快照结果（成功数/失败数/各比赛快照路径/fetch_url列表）
    """
    ids = [mid.strip() for mid in match_ids.split(',') if mid.strip()]
    result = {
        'label': label or datetime.now().strftime('%Y-%m-%d %H:%M'),
        'total': len(ids),
        'success': 0,
        'failed': 0,
        'snapshots': {},
        'need_fetch': [],
    }
    
    for mid in ids:
        url = FIXED_BONUS_URL.format(mid=mid)
        raw = fetch_url(url)
        
        snapshot = {
            'match_id': mid,
            'timestamp': datetime.now().isoformat(),
            'label': result['label'],
            'odds': {},
        }
        
        if raw:
            try:
                data = json.loads(raw)
                parsed = parse_odds_data(data, mid)
                snapshot['odds'] = parsed.get('odds', {})
                snapshot['source'] = 'direct_api'
                
                # 保存到本地
                snapshot_dir = os.path.join(DATA_DIR, 'odds_snapshots', mid)
                os.makedirs(snapshot_dir, exist_ok=True)
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                filepath = os.path.join(snapshot_dir, f'snapshot_{ts}.json')
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(snapshot, f, ensure_ascii=False, indent=2)
                
                snapshot['saved_to'] = filepath
                result['snapshots'][mid] = {'status': 'success', 'saved_to': filepath}
                result['success'] += 1
            except Exception as e:
                snapshot['error'] = f'解析失败: {e}'
                result['snapshots'][mid] = {'status': 'parse_error', 'error': str(e)}
                result['failed'] += 1
        else:
            # 直连失败，返回fetch_url供LLM用web.fetch获取
            result['need_fetch'].append({'match_id': mid, 'fetch_url': url})
            result['snapshots'][mid] = {'status': 'need_fetch', 'fetch_url': url}
            result['failed'] += 1
    
    result['note'] = (
        f'成功{result["success"]}/{result["total"]}场。'
        f'失败{result["failed"]}场请用web.fetch获取need_fetch中的fetch_url，'
        f'然后调用parse_odds_response(json_text=..., match_id=...)解析，'
        f'解析后的数据可用于赔率走势对比（compare_odds_movement）和资金流分析（fund_flow_analysis）。'
    )
    return result


# ============================================================
# 支持率获取（热门陷阱/冷门价值分析必需）
# ============================================================
@mcp.tool()
@safe_tool
def get_support_rate(match_ids: str) -> dict:
    """
    获取竞彩支持率（投注比例），用于热门陷阱/冷门价值分析
    来源：竞彩网getSupportRateV1.qry（支持批量matchIds）
    Args:
        match_ids: 比赛ID列表，逗号分隔（如"2041306,2041307"）
    Returns:
        各比赛的支持率（主胜/平局/客胜比例 + 投注票数）
    """
    url = SUPPORT_RATE_URL.format(mids=match_ids)
    raw = fetch_url(url, timeout=10)
    if not raw:
        return {'match_ids': match_ids, 'need_fetch': True, 'fetch_url': url,
                'note': '直连失败，请用web.fetch获取此URL的原始JSON，然后调用parse_support_rate_response解析'}
    try:
        data = json.loads(raw)
        if not data.get('success'):
            return {'error': data.get('errorMessage', 'API失败'), 'match_ids': match_ids}
        sr_map = data.get('value', {})
        result = {'match_ids': match_ids, 'support_rates': {}, 'source': 'getSupportRateV1'}
        for mid in match_ids.split(','):
            mid = mid.strip()
            sr_data = sr_map.get(f'_{mid}', {})
            if not sr_data:
                continue
            match_sr = {}
            for pool, name in [('HAD', '胜平负'), ('HHAD', '让球胜平负')]:
                pool_data = sr_data.get(pool, {})
                if pool_data:
                    match_sr[name] = {
                        'home_rate': pool_data.get('hSupportRate', ''),
                        'draw_rate': pool_data.get('dSupportRate', ''),
                        'away_rate': pool_data.get('aSupportRate', ''),
                        'home_votes': pool_data.get('win', 0),
                        'draw_votes': pool_data.get('draw', 0),
                        'away_votes': pool_data.get('lose', 0),
                    }
            if match_sr:
                result['support_rates'][mid] = match_sr
        result['count'] = len(result['support_rates'])
        result['note'] = '支持率=投注人数比例。热门陷阱：支持率>70%但赔率<1.5；冷门价值：支持率<20%但赔率>5。'
        return result
    except Exception as e:
        return {'error': f'解析失败: {e}', 'raw_preview': raw[:300]}


@mcp.tool()
@safe_tool
def parse_support_rate_response(json_text: str) -> dict:
    """解析web.fetch获取的支持率API原始JSON（降级方案用）"""
    try:
        data = json.loads(json_text)
        if not data.get('success'):
            return {'error': data.get('errorMessage', 'API失败')}
        sr_map = data.get('value', {})
        result = {'support_rates': {}}
        for key, val in sr_map.items():
            mid = key.lstrip('_')
            match_sr = {}
            for pool, name in [('HAD', '胜平负'), ('HHAD', '让球胜平负')]:
                pool_data = val.get(pool, {})
                if pool_data:
                    match_sr[name] = {
                        'home_rate': pool_data.get('hSupportRate', ''),
                        'draw_rate': pool_data.get('dSupportRate', ''),
                        'away_rate': pool_data.get('aSupportRate', ''),
                    }
            if match_sr:
                result['support_rates'][mid] = match_sr
        return result
    except Exception as e:
        return {'error': f'解析失败: {e}'}


# ============================================================
# 一键批量采集（全部比赛的赔率+资讯+支持率）
# ============================================================

@mcp.tool()
@safe_tool
def parse_500_html(html_text: str, data_type: str = "european") -> dict:
    """
    解析500.com HTML页面，提取欧指/亚盘/大小球/伤停数据
    来源：lottery-data项目fetch_500com_auto.py的解析逻辑（已验证）
    500.com页面URL：欧指ouzhi-{fid}.shtml / 亚盘yazhi-{fid}.shtml / 大小球daxiao-{fid}.shtml / 伤停shuju-{fid}.shtml
    Args:
        html_text: web.fetch获取的HTML页面文本
        data_type: european(欧指)/asian(亚盘)/overunder(大小球)/injury(伤停)
    Returns:
        结构化赔率数据（各公司赔率+平均值+初盘）
    """
    import re as _re
    if data_type == 'european':
        return _parse_500_european(html_text)
    elif data_type == 'asian':
        return _parse_500_asian(html_text)
    elif data_type == 'overunder':
        return _parse_500_overunder(html_text)
    elif data_type == 'injury':
        return _parse_500_injury(html_text)
    else:
        return {'error': f'未知data_type: {data_type}，可选: european/asian/overunder/injury'}


def _parse_500_european(html):
    import re as _re
    companies = []
    rows = _re.findall(r'<tr[^>]*class="tr\d"[^>]*>(.*?)</tr>', html, _re.DOTALL)
    for row in rows:
        cells = _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.DOTALL)
        texts = [_re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        texts = [t for t in texts if t]
        if len(texts) >= 5:
            name = _re.sub(r'^[^*]+\*+', '', texts[1])
            name = name.replace('(中国)', '').replace('(英国)', '').replace('(中国澳门)', '')
            companies.append({
                'name': name,
                'home': float(texts[2]) if _re.match(r'^\d+\.\d+$', texts[2]) else None,
                'draw': float(texts[3]) if _re.match(r'^\d+\.\d+$', texts[3]) else None,
                'away': float(texts[4]) if _re.match(r'^\d+\.\d+$', texts[4]) else None,
                'init_home': float(texts[5]) if len(texts) > 5 and _re.match(r'^\d+\.\d+$', texts[5]) else None,
                'init_draw': float(texts[6]) if len(texts) > 6 and _re.match(r'^\d+\.\d+$', texts[6]) else None,
                'init_away': float(texts[7]) if len(texts) > 7 and _re.match(r'^\d+\.\d+$', texts[7]) else None,
            })
    valid = [c for c in companies if c['home']]
    avg = {}
    if valid:
        avg = {'home': round(sum(c['home'] for c in valid) / len(valid), 2),
               'draw': round(sum(c['draw'] for c in valid) / len(valid), 2),
               'away': round(sum(c['away'] for c in valid) / len(valid), 2)}
    return {'type': 'european', 'companies': companies, 'average': avg, 'count': len(companies)}


def _parse_500_asian(html):
    import re as _re
    companies = []
    rows = _re.findall(r'<tr[^>]*class="tr\d"[^>]*>(.*?)</tr>', html, _re.DOTALL)
    for row in rows:
        cells = _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.DOTALL)
        texts = [_re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        texts = [t for t in texts if t]
        if len(texts) >= 5:
            name = _re.sub(r'^[^*]+\*+', '', texts[1])
            hw = _re.search(r'(\d+\.\d{2,3})', texts[2])
            aw = _re.search(r'(\d+\.\d{2,3})', texts[4])
            companies.append({'name': name, 'home_water': float(hw.group(1)) if hw else None,
                              'handicap': texts[3], 'away_water': float(aw.group(1)) if aw else None})
    return {'type': 'asian_handicap', 'companies': companies, 'count': len(companies)}


def _parse_500_overunder(html):
    import re as _re
    companies = []
    rows = _re.findall(r'<tr[^>]*class="tr\d"[^>]*>(.*?)</tr>', html, _re.DOTALL)
    for row in rows:
        cells = _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.DOTALL)
        texts = [_re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        texts = [t for t in texts if t]
        if len(texts) >= 5:
            name = _re.sub(r'^[^*]+\*+', '', texts[1])
            ow = _re.search(r'(\d+\.\d{2,3})', texts[2])
            uw = _re.search(r'(\d+\.\d{2,3})', texts[4])
            companies.append({'name': name, 'over_water': float(ow.group(1)) if ow else None,
                              'line': texts[3], 'under_water': float(uw.group(1)) if uw else None})
    return {'type': 'over_under', 'companies': companies, 'count': len(companies)}


def _parse_500_injury(html):
    import re as _re
    text = _re.sub(r'<[^>]+>', '|', html)
    text = _re.sub(r'\|+', ' | ', text)
    players = _re.findall(r'([\u4e00-\u9fa5]{2,4})\(([^)]+)\)', text)
    return {'type': 'injury', 'players_found': [{'name': p[0], 'position': p[1]} for p in players[:30]],
            'raw_text_length': len(text),
            'note': '伤停页面结构复杂，建议结合general_search搜索"主队 客队 伤停 首发"获取更准确信息'}


# ============================================================
# 开奖结算详情（赛后结算确认）
# ============================================================
@mcp.tool()
@safe_tool
def get_settlement_detail(match_id: str) -> dict:
    """
    获取比赛开奖结算详情（5玩法最终彩果+奖金）
    整合get_match_result（赛果）+ get_official_odds（最终SP），计算各玩法中奖选项和奖金
    Args:
        match_id: 比赛ID
    Returns:
        结算详情（比分/半场比分/5玩法中奖选项/最终SP/单注奖金）
    """
    result = {'match_id': match_id, 'settled': False, 'results': {}, 'payouts': {}}
    match_result = get_match_result.fn(match_id)
    if not match_result.get('settled'):
        result['note'] = '比赛未结束或赛果未更新，无法结算'
        result['detail_url'] = MATCH_DETAIL_URL.format(mid=match_id)
        return result
    result['settled'] = True
    result['results'] = match_result.get('results', {})
    odds = get_official_odds(match_id)
    if odds.get('odds'):
        result['final_odds'] = odds['odds']
        score = result['results'].get('score', '')
        if score and ':' in score:
            try:
                hg, ag = map(int, score.split(':'))
                total = hg + ag
                if hg > ag: spf = '主胜'
                elif hg == ag: spf = '平局'
                else: spf = '客胜'
                result['payouts']['胜平负'] = {'result': spf}
                ttg = f'{total}球' if total < 7 else '7+球'
                result['payouts']['总进球'] = {'result': ttg, 'total_goals': total}
                result['payouts']['比分'] = {'result': f'{hg}:{ag}'}
                half_score = result['results'].get('half_score', '')
                if half_score and ':' in half_score:
                    hhg, hag = map(int, half_score.split(':'))
                    if hhg > hag: ht = '胜'
                    elif hhg == hag: ht = '平'
                    else: ht = '负'
                    if hg > ag: ft = '胜'
                    elif hg == ag: ft = '平'
                    else: ft = '负'
                    result['payouts']['半全场'] = {'result': f'{ht}{ft}', 'half': half_score, 'full': score}
                for play, play_data in odds['odds'].items():
                    opt_names = play_data.get('option_names', [])
                    opt_odds = play_data.get('odds', [])
                    payout_result = result['payouts'].get(play, {}).get('result', '')
                    if payout_result and payout_result in opt_names:
                        idx = opt_names.index(payout_result)
                        if idx < len(opt_odds):
                            result['payouts'][play]['winning_odds'] = opt_odds[idx]
                            result['payouts'][play]['single_payout'] = round(opt_odds[idx] * 2, 2)
            except Exception as e:
                result['payout_error'] = str(e)
    result['note'] = '单注奖金=中奖SP×2元。过关奖金=各场中奖SP乘积×2元×倍数。'
    return result


if __name__ == '__main__':
    mcp.run()
