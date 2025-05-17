#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import sys
import subprocess
import tempfile
import requests
import time

# 这个函数将在脚本外部被调用，用于获取数据
def get_mcp_data():
    """使用mcp4_get_bookshelf函数获取微信读书数据"""
    # 这个函数将由Cascade调用
    pass

# 直接使用MCP函数而不是通过命令行
def get_bookshelf_direct():
    """直接使用HTTP请求获取微信读书书架数据"""
    print("正在直接获取微信读书书架数据...")
    try:
        # 使用MCP服务获取书架数据
        url = "http://localhost:4711/api/mcp-server-weread/get_bookshelf"
        response = requests.post(url, json={})
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"成功获取书架数据，共有{len(data.get('books', []))}本书")
                
                # 保存数据到文件
                output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
                os.makedirs(output_dir, exist_ok=True)
                
                with open(os.path.join(output_dir, "bookshelf.json"), 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"书架数据已保存到 {os.path.join(output_dir, 'bookshelf.json')}")
                
                return data
            except json.JSONDecodeError as e:
                print(f"解析JSON数据失败: {str(e)}")
                print(f"原始响应内容: {response.text[:500]}..." if len(response.text) > 500 else f"原始响应内容: {response.text}")
                return None
        else:
            print(f"请求失败，状态码: {response.status_code}")
            print(f"响应内容: {response.text[:500]}..." if len(response.text) > 500 else f"响应内容: {response.text}")
            return None
    except Exception as e:
        print(f"获取书架数据时出错: {str(e)}")
        return None

def fetch_bookshelf():
    """使用MCP服务获取微信读书书架数据"""
    print("正在获取微信读书书架数据...")
    
    # 首先尝试直接获取
    data = get_bookshelf_direct()
    if data:
        return data
    
    # 如果直接获取失败，则尝试通过命令行获取
    print("直接获取失败，尝试通过命令行获取...")
    
    # 创建临时文件来存储命令输出
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
        temp_filename = temp_file.name
    
    try:
        # 使用npx运行MCP服务并将输出保存到临时文件
        cmd = f"npx -y mcp-server-weread get_bookshelf"
        env = os.environ.copy()
        env["CC_URL"] = "https://cc.chenge.ink"
        env["CC_ID"] = "tFJoo75b1LFnRhfrzdxq3e"
        env["CC_PASSWORD"] = "ejkGrvUehJ76nZm5KizikH"
        
        print(f"执行命令: {cmd}")
        result = subprocess.run(cmd, shell=True, env=env, capture_output=True, text=True)
        print(f"命令执行结果: 返回码={result.returncode}")
        print(f"标准输出: {result.stdout[:500]}..." if len(result.stdout) > 500 else f"标准输出: {result.stdout}")
        print(f"标准错误: {result.stderr[:500]}..." if len(result.stderr) > 500 else f"标准错误: {result.stderr}")
        
        # 尝试解析输出
        try:
            # 尝试从stdout解析JSON
            data = json.loads(result.stdout)
            print(f"成功从stdout解析JSON数据")
        except json.JSONDecodeError:
            print(f"从stdout解析JSON失败，尝试从stderr解析")
            try:
                # 有时候JSON可能输出到stderr
                data = json.loads(result.stderr)
                print(f"成功从stderr解析JSON数据")
            except json.JSONDecodeError:
                print(f"解析JSON数据失败")
                return None
        
        # 保存数据到文件
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(output_dir, exist_ok=True)
        
        with open(os.path.join(output_dir, "bookshelf.json"), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"书架数据已保存到 {os.path.join(output_dir, 'bookshelf.json')}")
        
        return data
    except Exception as e:
        print(f"获取书架数据时出错: {str(e)}")
        return None

def fetch_book_notes(book_id):
    """使用MCP服务获取指定书籍的笔记和划线"""
    print(f"正在获取书籍 {book_id} 的笔记和划线...")
    
    # 创建临时文件来存储命令输出
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
        temp_filename = temp_file.name
    
    try:
        # 使用npx运行MCP服务并将输出保存到临时文件
        cmd = f"npx -y mcp-server-weread get_book_notes_and_highlights book_id={book_id} > {temp_filename}"
        env = os.environ.copy()
        env["CC_URL"] = "https://cc.chenge.ink"
        env["CC_ID"] = "tFJoo75b1LFnRhfrzdxq3e"
        env["CC_PASSWORD"] = "ejkGrvUehJ76nZm5KizikH"
        
        subprocess.run(cmd, shell=True, env=env, check=True)
        
        # 读取临时文件内容
        with open(temp_filename, 'r') as f:
            data = f.read()
        
        # 解析JSON数据
        try:
            notes_data = json.loads(data)
            
            # 保存数据到文件
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "books")
            os.makedirs(output_dir, exist_ok=True)
            
            with open(os.path.join(output_dir, f"{book_id}.json"), 'w', encoding='utf-8') as f:
                json.dump(notes_data, f, ensure_ascii=False, indent=2)
            print(f"书籍 {book_id} 的笔记和划线已保存到 {os.path.join(output_dir, f'{book_id}.json')}")
            
            return notes_data
        except json.JSONDecodeError:
            print("解析JSON数据失败，MCP服务可能返回了非JSON格式的数据")
            print(f"原始数据: {data[:200]}...")
            return None
    except Exception as e:
        print(f"获取书籍笔记时出错: {str(e)}")
        return None
    finally:
        # 删除临时文件
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

def fetch_all_data():
    """获取所有微信读书数据"""
    # 获取书架数据
    bookshelf_data = fetch_bookshelf()
    if not bookshelf_data:
        print("获取书架数据失败，无法继续获取书籍笔记")
        return
    
    # 获取每本书的笔记和划线
    books = bookshelf_data.get("books", [])
    for i, book in enumerate(books):
        book_id = book.get("bookId")
        if book_id:
            print(f"[{i+1}/{len(books)}] 正在获取书籍《{book.get('title')}》的笔记和划线...")
            fetch_book_notes(book_id)

if __name__ == "__main__":
    fetch_all_data()
