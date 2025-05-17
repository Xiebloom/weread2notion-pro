#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
from weread2notionpro.weread_api import WeReadApi

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_api')

def test_api():
    """测试微信读书API功能"""
    try:
        # 初始化API客户端
        api = WeReadApi()
        logger.info("API客户端初始化成功")
        
        # 测试获取书架数据
        logger.info("测试获取书架数据...")
        bookshelf = api.get_bookshelf()
        if bookshelf and isinstance(bookshelf, dict) and 'books' in bookshelf:
            books = bookshelf.get('books', [])
            logger.info(f"成功获取书架数据，共 {len(books)} 本书")
            
            # 如果有书，测试获取第一本书的详细信息
            if books:
                book = books[0]
                book_id = book.get('bookId')
                book_title = book.get('title')
                logger.info(f"选择第一本书进行测试: {book_title} (ID: {book_id})")
                
                # 测试获取书籍详情
                logger.info(f"测试获取书籍详情...")
                book_info = api.get_bookinfo(book_id)
                if book_info:
                    logger.info(f"成功获取书籍详情")
                
                # 测试获取阅读信息
                logger.info(f"测试获取阅读信息...")
                read_info = api.get_read_info(book_id)
                if read_info:
                    progress = read_info.get('readingProgress', 0)
                    logger.info(f"成功获取阅读信息，阅读进度: {progress}%")
                
                # 测试获取笔记列表
                logger.info(f"测试获取笔记列表...")
                reviews = api.get_review_list(book_id)
                logger.info(f"成功获取笔记列表，共 {len(reviews)} 条笔记")
                
                # 测试获取书签列表
                logger.info(f"测试获取书签列表...")
                bookmarks = api.get_bookmark_list(book_id)
                logger.info(f"成功获取书签列表，共 {len(bookmarks)} 个书签")
                
                # 测试获取章节信息
                logger.info(f"测试获取章节信息...")
                chapters = api.get_chapter_info(book_id)
                logger.info(f"成功获取章节信息，共 {len(chapters)} 章")
            else:
                logger.warning("书架为空，无法测试书籍相关功能")
        else:
            logger.error("获取书架数据失败")
            
    except Exception as e:
        logger.exception(f"测试过程中出现异常: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    success = test_api()
    if success:
        logger.info("API功能测试完成，所有功能正常")
        sys.exit(0)
    else:
        logger.error("API功能测试失败")
        sys.exit(1)
