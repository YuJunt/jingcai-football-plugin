#!/usr/bin/env python3
"""
历史数据增量更新合并器（字段严格对齐现有history JSON）
工作模式：football-data.co.uk直连被数据中心IP封禁(503)，
由LLM用web.fetch通道下载CSV到 downloads/ 目录，本脚本负责转换+增量合并去重。

用法：
  python3 merge_csv_update.py --csv downloads/E0_2627.csv --league E0        # 合并单个CSV
  python3 merge_csv_update.py --dir downloads/                               # 批量合并目录
  python3 merge_csv_update.py --status                                       # 查看各联赛数据状态
  python3 merge_csv_update.py --try-direct --league E0 --season 2627         # 尝试直连(可能503)

字段映射严格对齐现有 *_history.json：hthg/htag/htr/b365_home/books/ah_*/ou_* 等
支持2026-27新赛季原生xG字段 HxG/AxG → hxg/axg
"""
import argparse, csv, io, json, os, sys, urllib.request
from datetime import datetime

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_DIR = os.path.join(DATA_DIR, 'history')
DOWNLOAD_DIR = os.path.join(DATA_DIR, 'downloads')

# 博彩公司列前缀 → books字典key（初盘H/D/A，终盘CH/CD/CA）
BOOK_PREFIX = {'B365':'b365','BW':'bw','PS':'ps','WH':'wh','IW':'iw','VC':'vc',
               'PB':'pb','LB':'lb','BS':'bs','SB':'sb','GB':'gb'}

def fnum(v, default=0.0):
    try:
        if v is None or str(v).strip()=='' : return default
        return float(v)
    except: return default

def inum(v, default=0):
    try:
        if v is None or str(v).strip()=='': return default
        return int(float(v))
    except: return default

def parse_csv(content, league):
    """CSV → 与现有history JSON字段严格对齐的记录列表"""
    reader = csv.DictReader(io.StringIO(content))
    out = []
    for row in reader:
        if not row.get('Date') or not row.get('HomeTeam'): continue
        m = {
            'date': row.get('Date','').strip(),
            'home': row.get('HomeTeam','').strip(),
            'away': row.get('AwayTeam','').strip(),
            'home_goals': inum(row.get('FTHG')), 'away_goals': inum(row.get('FTAG')),
            'result': row.get('FTR','').strip(),
            'b365_home': fnum(row.get('B365H')), 'b365_draw': fnum(row.get('B365D')),
            'b365_away': fnum(row.get('B365A')),
            'books': {}, 'books_close': {},
            'max_home': fnum(row.get('MaxH')), 'max_draw': fnum(row.get('MaxD')),
            'max_away': fnum(row.get('MaxA')),
            'avg_home': fnum(row.get('AvgH')), 'avg_draw': fnum(row.get('AvgD')),
            'avg_away': fnum(row.get('AvgA')),
            'ah_handicap': fnum(row.get('AHh')),
            'ah_home': fnum(row.get('AHh')), 'ah_away': None,
            'ah_close_h': None, 'ah_close_a': None,
            'ou_line': None,
            'ou_max_over': fnum(row.get('Max>2.5')), 'ou_max_under': fnum(row.get('Max<2.5')),
            'ou_avg_over': fnum(row.get('Avg>2.5')), 'ou_avg_under': fnum(row.get('Avg<2.5')),
            'div': row.get('Div', league).strip() or league,
            'hthg': inum(row.get('HTHG')), 'htag': inum(row.get('HTAG')), 'htr': row.get('HTR','').strip(),
            'max_close_h': fnum(row.get('MaxCH')), 'max_close_d': fnum(row.get('MaxCD')),
            'max_close_a': fnum(row.get('MaxCA')),
            'avg_close_h': fnum(row.get('AvgCH')), 'avg_close_d': fnum(row.get('AvgCD')),
            'avg_close_a': fnum(row.get('AvgCA')),
            'bfe_h': fnum(row.get('BFEH')) or None, 'bfe_d': fnum(row.get('BFED')) or None,
            'bfe_a': fnum(row.get('BFEA')) or None,
            'bfe_close_h': fnum(row.get('BFECH')) or None, 'bfe_close_d': fnum(row.get('BFECD')) or None,
            'bfe_close_a': fnum(row.get('BFECA')) or None,
            'ou_b365_over': fnum(row.get('B365>2.5')), 'ou_b365_under': fnum(row.get('B365<2.5')),
            'ou_p_over': fnum(row.get('P>2.5')), 'ou_p_under': fnum(row.get('P<2.5')),
            'ou_close_b365_over': fnum(row.get('B365C>2.5')), 'ou_close_b365_under': fnum(row.get('B365C<2.5')),
            'ou_close_max_over': fnum(row.get('MaxC>2.5')), 'ou_close_max_under': fnum(row.get('MaxC<2.5')),
            'ah_b365_h': fnum(row.get('B365AHH')), 'ah_b365_a': fnum(row.get('B365AHA')),
            'ah_p_h': fnum(row.get('PAHH')), 'ah_p_a': fnum(row.get('PAHA')),
            'ah_close_p_h': fnum(row.get('PCAHH')), 'ah_close_p_a': fnum(row.get('PCAHA')),
            'ah_max_h': fnum(row.get('MaxAHH')), 'ah_max_a': fnum(row.get('MaxAHA')),
            'ah_avg_h': fnum(row.get('AvgAHH')), 'ah_avg_a': fnum(row.get('AvgAHA')),
            'ah_close_b365_h': fnum(row.get('B365CAHH')), 'ah_close_b365_a': fnum(row.get('B365CAHA')),
            'ah_close_max_h': fnum(row.get('MaxCAHH')), 'ah_close_max_a': fnum(row.get('MaxCAHA')),
            'ah_close_avg_h': fnum(row.get('AvgCAHH')), 'ah_close_avg_a': fnum(row.get('AvgCAHA')),
            'ah_bfe_h': None, 'ah_bfe_a': None, 'ah_close_bfe_h': None, 'ah_close_bfe_a': None,
            'attendance': inum(row.get('Attendance')), 'referee': (row.get('Referee') or '').strip(),
            'hs': inum(row.get('HS')), 'as': inum(row.get('AS')),
            'hst': inum(row.get('HST')), 'ast': inum(row.get('AST')),
            'hhw': inum(row.get('HHW')), 'ahw': inum(row.get('AHW')),
            'hc': inum(row.get('HC')), 'ac': inum(row.get('AC')),
            'hf': inum(row.get('HF')), 'af': inum(row.get('AF')),
            'ho': inum(row.get('HO')), 'ao': inum(row.get('AO')),
            'hy': inum(row.get('HY')), 'ay': inum(row.get('AY')),
            'hr': inum(row.get('HR')), 'ar': inum(row.get('AR')),
            'hbp': inum(row.get('HP')), 'abp': inum(row.get('AP')),
        }
        # 原生xG（2026-27新赛季起football-data提供 HxG/AxG）
        hxg, axg = fnum(row.get('HxG')) or None, fnum(row.get('AxG')) or None
        if hxg is not None: m['hxg'] = hxg
        if axg is not None: m['axg'] = axg
        # books多公司初盘/终盘
        for pref, key in BOOK_PREFIX.items():
            h,d,a = fnum(row.get(pref+'H')),fnum(row.get(pref+'D')),fnum(row.get(pref+'A'))
            if h and d and a: m['books'][key]={'h':h,'d':d,'a':a}
            ch,cd,ca = fnum(row.get(pref+'CH')),fnum(row.get(pref+'CD')),fnum(row.get(pref+'CA'))
            if ch and cd and ca: m['books_close'][key]={'h':ch,'d':cd,'a':ca}
        m['season'] = row.get('season','')
        out.append(m)
    return out

def load_history(league):
    p = os.path.join(HISTORY_DIR, f'{league}_history.json')
    if os.path.exists(p):
        with open(p,'r',encoding='utf-8') as f: return json.load(f), p
    return [], p

def merge(league, new_matches, season_tag=''):
    existing, path = load_history(league)
    # 去重key：date+home+away
    exist_keys = {(m.get('date'),m.get('home'),m.get('away')) for m in existing}
    added = updated = 0
    for nm in new_matches:
        if season_tag: nm['season']=season_tag
        key=(nm['date'],nm['home'],nm['away'])
        if key in exist_keys:
            # 更新已有记录（补全字段，新数据覆盖）
            for i,m in enumerate(existing):
                if (m.get('date'),m.get('home'),m.get('away'))==key:
                    existing[i]={**m,**nm}; updated+=1; break
        else:
            existing.append(nm); exist_keys.add(key); added+=1
    # 按日期排序
    def pd(s):
        for fmt in ['%d/%m/%Y','%Y-%m-%d']:
            try: return datetime.strptime(s,fmt)
            except: pass
        return datetime.min
    existing.sort(key=lambda m: pd(m.get('date','')))
    with open(path,'w',encoding='utf-8') as f:
        json.dump(existing,f,ensure_ascii=False)
    return added, updated, len(existing)

def process_csv(csv_path, league=None, season_tag=''):
    fname=os.path.basename(csv_path)
    if league is None:
        league=fname.split('_')[0]
    with open(csv_path,'r',encoding='utf-8',errors='replace') as f:
        content=f.read()
    rows=parse_csv(content,league)
    added,updated,total=merge(league,rows,season_tag)
    print(f'  {fname} → {league}: 解析{len(rows)}场, 新增{added}, 更新{updated}, 现共{total}场')
    return added,updated,total

def try_direct(league, season):
    url=f'https://www.football-data.co.uk/mmz4281/{season}/{league}.csv'
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=20) as r:
            content=r.read().decode('utf-8','replace')
        if content.lstrip().startswith('<'):
            print(f'  ❌ {league} {season}: 返回HTML（被503拦截），请改用web.fetch下载到downloads/')
            return
        os.makedirs(DOWNLOAD_DIR,exist_ok=True)
        p=os.path.join(DOWNLOAD_DIR,f'{league}_{season}.csv')
        with open(p,'w',encoding='utf-8') as f: f.write(content)
        process_csv(p,league,season)
    except Exception as e:
        print(f'  ❌ {league} {season} 直连失败: {str(e)[:60]}（请用web.fetch通道）')

def load_source_map():
    p=os.path.join(DATA_DIR,'league_source_map.json')
    if os.path.exists(p):
        with open(p,'r',encoding='utf-8') as f: return json.load(f)
    return {}

def print_urls(which='all'):
    """输出各联赛当前应下载的URL清单（LLM逐个用web.fetch下载到downloads/）"""
    sm=load_source_map(); leagues=sm.get('leagues',{})
    print('# 下载方式：web.fetch获取下列URL完整CSV → Write到 data/downloads/<Div>_<season>.csv → 运行 --dir data/downloads 批量合并')
    print('# 直连(curl/requests)被503封IP，必须走web.fetch；link fetch error是间歇抖动，重试即可；某联赛2627未发布就等几天\n')
    for div,info in leagues.items():
        season='2627' if info.get('format')=='cross_year' else '2526'
        url=f"https://www.football-data.co.uk/mmz4281/{season}/{info['fd_code']}.csv"
        print(f"{div:<5}{info['name']:<6}{season}  {url}")

def status():
    print(f'{"联赛":<6}{"场次":>7}{"最新日期":>13}{"有射门":>7}{"有xG":>6}')
    print('-'*45)
    import glob
    for fp in sorted(glob.glob(os.path.join(HISTORY_DIR,'*_history.json'))):
        lg=os.path.basename(fp).replace('_history.json','')
        d=json.load(open(fp))
        def pd(s):
            for fmt in ['%d/%m/%Y','%Y-%m-%d']:
                try:return datetime.strptime(s,fmt)
                except:pass
            return datetime.min
        ds=[pd(m.get('date','')) for m in d if m.get('date')]
        latest=max(ds).strftime('%Y-%m-%d') if ds else '?'
        shots=sum(1 for m in d if m.get('hs'))
        xg=sum(1 for m in d if m.get('hxg'))
        print(f'{lg:<6}{len(d):>7}{latest:>13}{shots:>7}{xg:>6}')

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--csv'); ap.add_argument('--dir'); ap.add_argument('--league')
    ap.add_argument('--season', default=''); ap.add_argument('--status',action='store_true')
    ap.add_argument('--urls',action='store_true',help='输出所有联赛当前下载URL清单')
    ap.add_argument('--try-direct',action='store_true')
    a=ap.parse_args()
    if a.urls: print_urls()
    elif a.status: status()
    elif a.try_direct and a.league:
        try_direct(a.league,a.season or '2627')
    elif a.csv: process_csv(a.csv,a.league,a.season)
    elif a.dir:
        import glob
        ta=tu=0
        for p in sorted(glob.glob(os.path.join(a.dir,'*.csv'))):
            x,y,_=process_csv(p,None,a.season); ta+=x;tu+=y
        print(f'\n批量合并完成：共新增{ta}，更新{tu}')
    else: ap.print_help()
