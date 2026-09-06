#!/usr/bin/env python3
"""自动更新封装Skill的SKILL.md（版本、服务器列表、技能列表、工具数）"""
import json
import os
import re
import sys

PLUGIN_ROOT = "/home/user/.super_doubao/super-doubao-runtime/workspace/jingcai-football-plugin"
SKILL_ROOT = "/home/user/.super_doubao/super-doubao-runtime/workspace/.user_skills/jingcai-football-plugin-skill"

def main():
    # 读取版本
    with open(os.path.join(PLUGIN_ROOT, 'plugin.json'), 'r') as f:
        plugin = json.load(f)
    version = plugin['version']
    
    # 统计服务器和工具
    servers = []
    total_tools = 0
    for server_dir in sorted(os.listdir(os.path.join(PLUGIN_ROOT, 'servers'))):
        server_path = os.path.join(PLUGIN_ROOT, 'servers', server_dir)
        server_py = os.path.join(server_path, 'server.py')
        if os.path.isdir(server_path) and os.path.exists(server_py):
            with open(server_py, 'r') as f:
                tool_count = f.read().count('@mcp.tool')
            servers.append((server_dir, tool_count))
            total_tools += tool_count
    
    # 统计技能
    skills = []
    for skill_dir in sorted(os.listdir(os.path.join(PLUGIN_ROOT, 'skills'))):
        skill_path = os.path.join(PLUGIN_ROOT, 'skills', skill_dir)
        skill_md = os.path.join(skill_path, 'SKILL.md')
        if os.path.isdir(skill_path) and os.path.exists(skill_md):
            skills.append(skill_dir)
    
    skill_count = len(skills)
    server_count = len(servers)
    
    # 读取封装Skill的SKILL.md
    skill_md_path = os.path.join(SKILL_ROOT, 'SKILL.md')
    with open(skill_md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 更新版本号
    content = re.sub(r'plugin-version: [\d.]+', f'plugin-version: {version}', content)
    content = re.sub(r'wrapper-version: [\d.]+', 'wrapper-version: 1.3.0', content)
    
    # 更新description
    content = re.sub(r'插件v[\d.]+', f'插件v{version}', content)
    content = re.sub(r'\d+个技能（[^）]*）', f'{skill_count}个技能（1核心+1方法论+5玩法专属+1混合过关）', content)
    content = re.sub(r'\d+个MCP服务器（\d+个工具）', f'{server_count}个MCP服务器（{total_tools}个工具）', content)
    
    # 更新能力列表
    skill_names = '、'.join(skills)
    content = re.sub(r'提供以下能力：[^。]+', f'提供以下能力：{skill_names}', content)
    
    # 更新MCP服务器列表（支持列表和表格两种格式）
    server_lines = []
    for server_name, tool_count in servers:
        server_lines.append(f'- **{server_name}**（{tool_count}工具）：transport=stdio，启动命令 `python3 ./servers/{server_name}/server.py`')
    new_server_section = f'### MCP 服务器（{server_count}个）\n\n' + '\n'.join(server_lines) + '\n'
    
    # 尝试匹配列表格式
    pattern_list = r'### MCP 服务器[^\n]*\n\n(?:- \*\*[^*]+\*\*[^`]+`\n)+'
    # 尝试匹配表格格式（从### MCP到下一个###或##）
    pattern_table = r'### MCP 服务器[^\n]*\n\n\|[^\n]+\n(?:\|[^\n]+\n)+'
    
    if re.search(pattern_list, content):
        content = re.sub(pattern_list, new_server_section, content)
        print(f'  ✅ MCP服务器列表（列表格式）已更新（{server_count}个）')
    elif re.search(pattern_table, content):
        content = re.sub(pattern_table, new_server_section, content)
        print(f'  ✅ MCP服务器列表（表格格式）已更新（{server_count}个）')
    else:
        print('  ⚠️  未找到MCP服务器列表，跳过')
    
    # 写回
    with open(skill_md_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f'  ✅ SKILL.md已更新（v{version}, {skill_count}技能, {server_count}服务器, {total_tools}工具）')

if __name__ == '__main__':
    main()
