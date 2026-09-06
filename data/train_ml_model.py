#!/usr/bin/env python3
"""
ML集成模型训练脚本（P2-1）
用10万场免费历史数据训练GradientBoosting模型，预测1X2结果
不需要xgboost，使用sklearn的GradientBoostingClassifier（效果接近）

特征工程：
- 主队近5场场均进球/失球/射门/射正
- 客队近5场场均进球/失球/射门/射正
- 赔率隐含概率（主/平/客）
- 主场优势
- Elo差分（简化版：用近期胜率差近似）

用法：
  python3 train_ml_model.py              # 训练并保存模型
  python3 train_ml_model.py --evaluate   # 训练并输出准确率评估
"""
import json
import os
import sys
import glob
import argparse
from collections import defaultdict
from datetime import datetime

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_DIR = os.path.join(DATA_DIR, 'history')
MODEL_PATH = os.path.join(DATA_DIR, 'ml_model.pkl')

def parse_date(date_str):
    """解析日期，支持DD/MM/YYYY格式"""
    for fmt in ['%d/%m/%Y', '%Y-%m-%d']:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue
    return None

def build_features_for_league(matches, league_code):
    """为一个联赛构建特征和标签"""
    # 按日期排序
    matches_sorted = sorted(matches, key=lambda m: parse_date(m.get('date', '')) or datetime.min)
    
    # 球队历史记录（滚动窗口）
    team_history = defaultdict(list)
    
    features = []
    labels = []
    
    for m in matches_sorted:
        home = m.get('home', '')
        away = m.get('away', '')
        hg = m.get('home_goals', 0)
        ag = m.get('away_goals', 0)
        result = m.get('result', '')
        
        if not home or not away or result not in ['H', 'D', 'A']:
            continue
        
        # 获取两队近5场统计
        def get_recent_stats(team, n=5):
            history = team_history.get(team, [])[-n:]
            if len(history) < 3:
                return None
            stats = {
                'avg_gf': sum(h['gf'] for h in history) / len(history),
                'avg_ga': sum(h['ga'] for h in history) / len(history),
                'avg_shots': sum(h.get('shots', 0) for h in history) / len(history),
                'avg_sot': sum(h.get('sot', 0) for h in history) / len(history),
                'win_rate': sum(1 for h in history if h['result'] == 'W') / len(history),
            }
            return stats
        
        home_stats = get_recent_stats(home)
        away_stats = get_recent_stats(away)
        
        # 需要双方都有足够历史
        if not home_stats or not away_stats:
            # 更新历史后继续
            team_history[home].append({
                'gf': hg, 'ga': ag,
                'shots': m.get('hs', 0), 'sot': m.get('hst', 0),
                'result': 'W' if hg > ag else ('D' if hg == ag else 'L')
            })
            team_history[away].append({
                'gf': ag, 'ga': hg,
                'shots': m.get('as', 0), 'sot': m.get('ast', 0),
                'result': 'W' if ag > hg else ('D' if ag == hg else 'L')
            })
            continue
        
        # 赔率隐含概率
        b365_h = m.get('b365_home') or m.get('avg_home') or 0
        b365_d = m.get('b365_draw') or m.get('avg_draw') or 0
        b365_a = m.get('b365_away') or m.get('avg_away') or 0
        
        if b365_h and b365_d and b365_a:
            inv_sum = 1/b365_h + 1/b365_d + 1/b365_a
            imp_h = (1/b365_h) / inv_sum
            imp_d = (1/b365_d) / inv_sum
            imp_a = (1/b365_a) / inv_sum
        else:
            imp_h = imp_d = imp_a = 0.33
        
        # 构建特征向量
        feat = [
            home_stats['avg_gf'], home_stats['avg_ga'],
            away_stats['avg_gf'], away_stats['avg_ga'],
            home_stats['avg_shots'], home_stats['avg_sot'],
            away_stats['avg_shots'], away_stats['avg_sot'],
            home_stats['win_rate'] - away_stats['win_rate'],  # 近期状态差
            imp_h, imp_d, imp_a,  # 赔率隐含概率
            1.0,  # 主场优势（常数项）
            home_stats['avg_gf'] - away_stats['avg_ga'],  # 攻防匹配差
            away_stats['avg_gf'] - home_stats['avg_ga'],
        ]
        
        features.append(feat)
        labels.append(result)
        
        # 更新历史
        team_history[home].append({
            'gf': hg, 'ga': ag,
            'shots': m.get('hs', 0), 'sot': m.get('hst', 0),
            'result': 'W' if hg > ag else ('D' if hg == ag else 'L')
        })
        team_history[away].append({
            'gf': ag, 'ga': hg,
            'shots': m.get('as', 0), 'sot': m.get('ast', 0),
            'result': 'W' if ag > hg else ('D' if ag == hg else 'L')
        })
    
    return features, labels

def train_model(evaluate=False):
    """训练ML模型"""
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.model_selection import cross_val_score
    import numpy as np
    import pickle
    
    print("=" * 60)
    print("ML集成模型训练（GradientBoosting + RandomForest）")
    print("=" * 60)
    
    # 加载所有联赛数据
    all_features = []
    all_labels = []
    league_count = 0
    
    for filepath in sorted(glob.glob(os.path.join(HISTORY_DIR, '*_history.json'))):
        league = os.path.basename(filepath).replace('_history.json', '')
        with open(filepath, 'r', encoding='utf-8') as f:
            matches = json.load(f)
        
        feats, labels = build_features_for_league(matches, league)
        if len(feats) > 100:
            all_features.extend(feats)
            all_labels.extend(labels)
            league_count += 1
            print(f"  {league}: {len(feats)}个训练样本")
    
    print(f"\n总计: {league_count}个联赛, {len(all_features)}个训练样本")
    
    X = np.array(all_features)
    y = np.array(all_labels)
    
    # 处理NaN
    X = np.nan_to_num(X, nan=0.0)
    
    # 训练GradientBoosting
    print("\n训练GradientBoosting模型...")
    gb_model = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        random_state=42
    )
    gb_model.fit(X, y)
    
    # 训练RandomForest（集成用）
    print("训练RandomForest模型...")
    rf_model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        random_state=42,
        n_jobs=-1
    )
    rf_model.fit(X, y)
    
    # 训练集准确率
    gb_acc = gb_model.score(X, y)
    rf_acc = rf_model.score(X, y)
    print(f"\n训练集准确率: GB={gb_acc*100:.1f}%, RF={rf_acc*100:.1f}%")
    
    if evaluate:
        # 交叉验证
        print("\n5折交叉验证...")
        gb_cv = cross_val_score(gb_model, X, y, cv=5, scoring='accuracy')
        rf_cv = cross_val_score(rf_model, X, y, cv=5, scoring='accuracy')
        print(f"GB交叉验证准确率: {gb_cv.mean()*100:.1f}% (±{gb_cv.std()*100:.1f}%)")
        print(f"RF交叉验证准确率: {rf_cv.mean()*100:.1f}% (±{rf_cv.std()*100:.1f}%)")
        
        # 特征重要性
        feature_names = [
            '主队场均进球', '主队场均失球', '客队场均进球', '客队场均失球',
            '主队场均射门', '主队场均射正', '客队场均射门', '客队场均射正',
            '近期胜率差', '隐含主胜', '隐含平局', '隐含客胜',
            '主场优势', '主队攻防差', '客队攻防差'
        ]
        importances = gb_model.feature_importances_
        sorted_idx = np.argsort(importances)[::-1]
        print("\n特征重要性Top10:")
        for i in sorted_idx[:10]:
            print(f"  {feature_names[i]}: {importances[i]*100:.1f}%")
    
    # 保存模型
    model_bundle = {
        'gradient_boosting': gb_model,
        'random_forest': rf_model,
        'feature_names': [
            'home_avg_gf', 'home_avg_ga', 'away_avg_gf', 'away_avg_ga',
            'home_avg_shots', 'home_avg_sot', 'away_avg_shots', 'away_avg_sot',
            'form_diff', 'imp_home', 'imp_draw', 'imp_away',
            'home_advantage', 'home_attack_vs_away_defense', 'away_attack_vs_home_defense'
        ],
        'training_samples': len(all_features),
        'leagues': league_count,
        'training_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'gb_train_accuracy': gb_acc,
        'rf_train_accuracy': rf_acc,
        'model_version': '1.0.0'
    }
    
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(model_bundle, f)
    
    print(f"\n模型已保存到: {MODEL_PATH}")
    print(f"文件大小: {os.path.getsize(MODEL_PATH)/1024:.0f}KB")
    
    return model_bundle

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ML模型训练')
    parser.add_argument('--evaluate', action='store_true', help='输出评估报告')
    args = parser.parse_args()
    train_model(evaluate=args.evaluate)
