import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

import requests
from requests.utils import cookiejar_from_dict
from retrying import retry
from urllib.parse import quote
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('weread_api')

# 加载环境变量
load_dotenv()

# API URL常量
WEREAD_URL = "https://weread.qq.com/"
WEREAD_API = {
    "notebooks": "https://weread.qq.com/web/user/notebooks",
    "bookshelf": "https://weread.qq.com/web/shelf/sync",
    "bookmarklist": "https://weread.qq.com/web/book/bookmarklist",
    "chapter_info": "https://weread.qq.com/web/book/chapterInfos",
    "read_info": "https://weread.qq.com/web/book/getProgress",
    "review_list": "https://weread.qq.com/web/review/list",
    "book_info": "https://weread.qq.com/web/book/info"
}


class WeReadApi:
    """微信读书API客户端
    
    提供对微信读书API的访问功能，支持从本地文件或API获取数据。
    """
    def __init__(self):
        """初始化微信读书API客户端
        
        获取Cookie并初始化会话。
        """
        self.cookie = self._get_cookie()
        self.session = requests.Session()
        self.session.cookies = self._parse_cookie_string()
        self.data_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "data"
        
        # 创建数据目录
        self.data_dir.mkdir(exist_ok=True)
        (self.data_dir / "books").mkdir(exist_ok=True)

    def _get_cookie_from_cloud(self, url: str, cloud_id: str, password: str) -> Optional[str]:
        """从 CookieCloud 服务获取 Cookie
        
        Args:
            url: CookieCloud 服务器URL
            cloud_id: CookieCloud ID
            password: CookieCloud 密码
            
        Returns:
            str: 如果成功，返回 Cookie 字符串，否则返回 None
        """
        if url.endswith("/"):
            url = url[:-1]
            
        req_url = f"{url}/get/{cloud_id}"
        data = {"password": password}
        
        try:
            response = requests.post(req_url, data=data)
            
            if response.status_code == 200:
                data = response.json()
                cookie_data = data.get("cookie_data")
                
                if not cookie_data:
                    logger.warning("CookieCloud 响应中没有 cookie_data 字段")
                    return None
                
                # 检查 weread.qq.com 或 weread 域名
                domain_key = None
                if "weread.qq.com" in cookie_data:
                    domain_key = "weread.qq.com"
                elif "weread" in cookie_data:
                    domain_key = "weread"
                
                if not domain_key:
                    logger.warning("在 CookieCloud 中没有找到微信读书的 Cookie")
                    return None
                
                cookies = cookie_data[domain_key]
                logger.info(f"从 CookieCloud 获取到 {len(cookies)} 个微信读书 Cookie")
                
                # 检查关键 Cookie
                has_vid = any(cookie['name'] == 'wr_vid' for cookie in cookies)
                has_skey = any(cookie['name'] == 'wr_skey' for cookie in cookies)
                
                if not has_vid or not has_skey:
                    logger.warning(f"Cookie 缺失关键值: wr_vid={has_vid}, wr_skey={has_skey}")
                
                # 生成 Cookie 字符串
                return "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
            else:
                logger.error(f"CookieCloud 请求失败: 状态码 {response.status_code}")
                return None
        except Exception as e:
            logger.exception(f"CookieCloud 请求异常: {str(e)}")
            return None

    def _get_cookie(self) -> str:
        """获取微信读书 Cookie
        
        优先级：
        1. 环境变量 WEREAD_COOKIE
        2. CookieCloud 服务
        
        Returns:
            str: Cookie 字符串
            
        Raises:
            Exception: 如果无法获取 Cookie
        """
        # 首先检查环境变量
        cookie = os.getenv("WEREAD_COOKIE")
        if cookie and cookie.strip():
            logger.info("从环境变量获取到 Cookie")
            return cookie
        
        # 尝试从 CookieCloud 获取
        url = os.getenv("CC_URL")
        cloud_id = os.getenv("CC_ID")
        password = os.getenv("CC_PASSWORD")
        
        if url and cloud_id and password:
            logger.info("尝试从 CookieCloud 获取 Cookie")
            cookie = self._get_cookie_from_cloud(url, cloud_id, password)
            if cookie:
                return cookie
        
        # 如果上述方法都失败，抛出异常
        raise Exception("无法获取微信读书 Cookie，请设置 WEREAD_COOKIE 环境变量或配置 CookieCloud")

    def _parse_cookie_string(self) -> requests.cookies.RequestsCookieJar:
        """解析 Cookie 字符串为 cookiejar
        
        Returns:
            RequestsCookieJar: 可用于 requests 的 cookiejar 对象
        """
        cookies_dict = {}
        pattern = re.compile(r'([^=]+)=([^;]+);?\s*')
        matches = pattern.findall(self.cookie)
        
        for key, value in matches:
            cookies_dict[key] = value
        
        return cookiejar_from_dict(cookies_dict)

    def get_bookshelf(self) -> Dict:
        """获取微信读书书架数据
        
        首先尝试从本地文件读取，如果文件不存在或读取失败，则从API获取。
        
        Returns:
            Dict: 书架数据
        """
        # 尝试从文件读取
        file_path = self._get_file_path('bookshelf')
        data = self._read_from_file(file_path)
        if data:
            return data
        
        # 从API获取
        logger.info("从API获取书架数据")
        try:
            # 访问主页初始化会话
            self.session.get(WEREAD_URL, headers=self._get_headers(is_api=False))
            
            # 设置请求参数
            params = {
                "synckey": 0,
                "teenmode": 0,
                "album": 1,
                "onlyBookid": 0
            }
            
            # 发送请求
            response = self._make_request(
                WEREAD_API["bookshelf"], 
                method="get", 
                params=params, 
                headers=self._get_headers(is_api=True, referer=WEREAD_URL)
            )
            
            if response.ok:
                data = response.json()
                
                # 如果成功获取数据，保存到文件
                if isinstance(data, dict) and ('books' in data or 'library' in data):
                    self._write_to_file(file_path, data)
                    
                    # 记录书籍数量
                    books_count = len(data.get('books', [])) if 'books' in data else 0
                    logger.info(f"成功获取书架数据: {books_count} 本书")
                    
                return data
            else:
                logger.error(f"获取书架数据失败: HTTP {response.status_code}")
                return {}
        except Exception as e:
            logger.exception(f"获取书架数据异常: {str(e)}")
            return {}

    def _get_headers(self, is_api=True, referer=None) -> Dict[str, str]:
        """获取请求头
        
        Args:
            is_api: 是否是API请求
            referer: 来源页面URL
            
        Returns:
            Dict[str, str]: 请求头字典
        """
        common_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }
        
        if is_api:
            headers = {
                **common_headers,
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://weread.qq.com",
                "Content-Type": "application/json;charset=UTF-8",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin"
            }
        else:
            headers = {
                **common_headers,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "cache-control": "no-cache",
                "pragma": "no-cache",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                "upgrade-insecure-requests": "1"
            }
        
        if referer:
            headers["Referer"] = referer
            
        return headers
    
    def _make_request(self, url: str, method: str = "get", params: Dict = None, 
                     data: Dict = None, headers: Dict = None) -> requests.Response:
        """发送API请求
        
        Args:
            url: 请求URL
            method: 请求方法，默认为get
            params: 请求参数
            data: 请求体数据
            headers: 请求头
            
        Returns:
            requests.Response: 请求响应
        """
        if params is None:
            params = {}
        
        # 添加时间戳参数避免缓存
        if method.lower() == "get":
            params["_"] = int(time.time() * 1000)
        
        if headers is None:
            headers = self._get_headers(is_api=True)
        
        logger.debug(f"API 请求: {method.upper()} {url}")
        
        try:
            if method.lower() == "get":
                response = self.session.get(url, params=params, headers=headers)
            else:
                response = self.session.post(url, json=data, params=params, headers=headers)
            
            logger.debug(f"API 响应: {response.status_code}")
            
            # 检查响应中的错误代码
            if response.ok and response.headers.get('Content-Type', '').startswith('application/json'):
                try:
                    json_data = response.json()
                    if isinstance(json_data, dict) and 'errcode' in json_data and json_data['errcode'] != 0:
                        self._handle_error_code(json_data['errcode'])
                except:
                    pass
            
            return response
        except Exception as e:
            logger.exception(f"API 请求异常: {str(e)}")
            raise
    
    def _handle_error_code(self, error_code: int) -> None:
        """处理API错误代码
        
        Args:
            error_code: 错误代码
        """
        error_messages = {
            -2012: "登录超时，Cookie可能已过期",
            -2010: "登录超时，Cookie可能已过期"
        }
        
        if error_code in error_messages:
            logger.error(f"API 错误: {error_messages[error_code]} (code: {error_code})")
        else:
            logger.error(f"API 错误: 未知错误 (code: {error_code})")
    
    def _get_file_path(self, file_type: str, book_id: str = None) -> Path:
        """获取数据文件路径
        
        Args:
            file_type: 文件类型，如 'bookshelf' 或 'book'
            book_id: 书籍ID，如果是书籍相关的文件则需要提供
            
        Returns:
            Path: 文件路径
        """
        if file_type == 'bookshelf':
            return self.data_dir / "bookshelf.json"
        elif file_type == 'book' and book_id:
            return self.data_dir / "books" / f"{book_id}.json"
        else:
            raise ValueError(f"无效的文件类型: {file_type}")
    
    def _read_from_file(self, file_path: Path) -> Optional[Dict]:
        """从文件读取数据
        
        Args:
            file_path: 文件路径
            
        Returns:
            Optional[Dict]: 如果成功，返回数据字典，否则返回 None
        """
        if not file_path.exists():
            logger.info(f"文件不存在: {file_path}")
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"从文件读取数据成功: {file_path}")
            return data
        except Exception as e:
            logger.exception(f"读取文件失败: {file_path}, 错误: {str(e)}")
            return None
    
    def _write_to_file(self, file_path: Path, data: Dict) -> bool:
        """将数据写入文件
        
        Args:
            file_path: 文件路径
            data: 要写入的数据
            
        Returns:
            bool: 是否成功
        """
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"数据写入文件成功: {file_path}")
            return True
        except Exception as e:
            logger.exception(f"写入文件失败: {file_path}, 错误: {str(e)}")
            return False
    
    def handle_errcode(self,errcode):
        if( errcode== -2012 or errcode==-2010):
            print(f"::error::微信读书Cookie过期了，请参考文档重新设置。https://mp.weixin.qq.com/s/B_mqLUZv7M1rmXRsMlBf7A")

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_notebooklist(self):
        """获取笔记本列表"""
        self.session.get(WEREAD_URL)
        r = self.session.get(WEREAD_NOTEBOOKS_URL)
        if r.ok:
            data = r.json()
            books = data.get("books")
            books.sort(key=lambda x: x["sort"])
            return books
        else:
            errcode = r.json().get("errcode",0)
            self.handle_errcode(errcode)
            raise Exception(f"Could not get notebook list {r.text}")

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_bookinfo(self, bookId: str) -> Dict:
        """获取书籍的详细信息
        
        首先尝试从本地文件读取，如果文件不存在或读取失败，则从API获取。
        
        Args:
            bookId: 书籍ID
            
        Returns:
            Dict: 书籍详情数据
        """
        # 尝试从文件读取
        file_path = self.data_dir / "books" / f"{bookId}_info.json"
        data = self._read_from_file(file_path)
        
        if data and isinstance(data, dict):
            logger.info(f"成功从文件读取书籍 {bookId} 的详情信息")
            return data
        
        # 从API获取
        logger.info(f"从API获取书籍 {bookId} 的详情信息")
        try:
            # 访问主页初始化会话
            self.session.get(WEREAD_URL, headers=self._get_headers(is_api=False))
            
            # 设置请求参数
            params = {"bookId": bookId}
            
            # 发送请求
            response = self._make_request(
                WEREAD_API["book_info"],
                method="get",
                params=params,
                headers=self._get_headers(is_api=True)
            )
            
            if response.ok:
                data = response.json()
                
                # 保存到文件
                self._write_to_file(file_path, data)
                
                logger.info(f"成功获取书籍 {bookId} 的详情信息")
                return data
            else:
                logger.error(f"获取书籍 {bookId} 的详情信息失败: HTTP {response.status_code}")
                return {}
        except Exception as e:
            logger.exception(f"获取书籍 {bookId} 的详情信息异常: {str(e)}")
            return {}


    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_bookmark_list(self, bookId: str) -> List[Dict]:
        """获取书籍的书签列表
        
        首先尝试从本地文件读取，如果文件不存在或读取失败，则从API获取。
        
        Args:
            bookId: 书籍ID
            
        Returns:
            List[Dict]: 书签列表
        """
        # 尝试从文件读取
        file_path = self.data_dir / "books" / f"{bookId}_bookmarks.json"
        data = self._read_from_file(file_path)
        
        if data and isinstance(data, dict) and "updated" in data:
            bookmarks = data.get("updated", [])
            logger.info(f"成功从文件读取书籍 {bookId} 的书签列表，共 {len(bookmarks)} 个书签")
            return bookmarks
        
        # 从API获取
        logger.info(f"从API获取书籍 {bookId} 的书签列表")
        try:
            # 访问主页初始化会话
            self.session.get(WEREAD_URL, headers=self._get_headers(is_api=False))
            
            # 设置请求参数
            params = {"bookId": bookId}
            
            referer = f"https://weread.qq.com/web/reader/{bookId}"
            
            # 发送请求
            response = self._make_request(
                WEREAD_API["bookmarklist"],
                method="get",
                params=params,
                headers=self._get_headers(is_api=True, referer=referer)
            )
            
            if response.ok:
                data = response.json()
                
                # 保存到文件
                self._write_to_file(file_path, data)
                
                bookmarks = data.get("updated", [])
                logger.info(f"成功获取书籍 {bookId} 的书签列表，共 {len(bookmarks)} 个书签")
                return bookmarks
            else:
                logger.error(f"获取书籍 {bookId} 的书签列表失败: HTTP {response.status_code}")
                return []
        except Exception as e:
            logger.exception(f"获取书籍 {bookId} 的书签列表异常: {str(e)}")
            return []

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_read_info(self, bookId: str) -> Dict:
        """获取书籍的阅读信息
        
        首先尝试从本地文件读取，如果文件不存在或读取失败，则从API获取。
        
        Args:
            bookId: 书籍ID
            
        Returns:
            Dict: 阅读信息数据
        """
        # 尝试从文件读取
        file_path = self._get_file_path('book', bookId)
        data = self._read_from_file(file_path)
        if data:
            return data
        
        # 从API获取
        logger.info(f"从API获取书籍 {bookId} 的阅读信息")
        try:
            # 访问主页初始化会话
            self.session.get(WEREAD_URL, headers=self._get_headers(is_api=False))
            
            # 设置请求参数
            params = {
                "noteCount": 1,
                "readingDetail": 1,
                "finishedBookIndex": 1,
                "readingBookCount": 1,
                "readingBookIndex": 1,
                "finishedBookCount": 1,
                "bookId": bookId,
                "finishedDate": 1
            }
            
            referer = f"https://weread.qq.com/web/reader/{bookId}"
            
            # 对于这个API，我们需要添加一些特殊的头信息
            headers = self._get_headers(is_api=True, referer=referer)
            headers.update({
                "baseapi": "32",
                "appver": "8.2.5.10163885",
                "basever": "8.2.5.10163885",
                "osver": "12"
            })
            
            # 发送请求
            response = self._make_request(
                WEREAD_API["read_info"],
                method="get",
                params=params,
                headers=headers
            )
            
            if response.ok:
                data = response.json()
                
                # 如果成功获取数据，保存到文件
                if isinstance(data, dict):
                    self._write_to_file(file_path, data)
                    logger.info(f"成功获取书籍 {bookId} 的阅读信息")
                
                return data
            else:
                logger.error(f"获取书籍 {bookId} 的阅读信息失败: HTTP {response.status_code}")
                return {}
        except Exception as e:
            logger.exception(f"获取书籍 {bookId} 的阅读信息异常: {str(e)}")
            return {}

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_review_list(self, bookId: str) -> List[Dict]:
        """获取书籍的笔记列表
        
        首先尝试从本地文件读取，如果文件不存在或读取失败，则从API获取。
        
        Args:
            bookId: 书籍ID
            
        Returns:
            List[Dict]: 笔记列表
        """
        # 尝试从文件读取
        file_path = self.data_dir / "books" / f"{bookId}.json"
        data = self._read_from_file(file_path)
        
        if data and isinstance(data, dict):
            # 从数据中提取笔记列表
            reviews = data.get("reviews", [])
            if reviews:
                reviews = list(map(lambda x: x.get("review") if isinstance(x, dict) and "review" in x else x, reviews))
                reviews = [
                    {"chapterUid": 1000000, **x} if x.get("type") == 4 else x
                    for x in reviews
                ]
                logger.info(f"成功从文件读取书籍 {bookId} 的笔记列表，共 {len(reviews)} 条笔记")
                return reviews
        
        # 从API获取
        logger.info(f"从API获取书籍 {bookId} 的笔记列表")
        try:
            # 访问主页初始化会话
            self.session.get(WEREAD_URL, headers=self._get_headers(is_api=False))
            
            # 设置请求参数
            params = {
                "bookId": bookId,
                "listType": 11,
                "mine": 1,
                "syncKey": 0
            }
            
            referer = f"https://weread.qq.com/web/reader/{bookId}"
            
            # 发送请求
            response = self._make_request(
                WEREAD_API["review_list"],
                method="get",
                params=params,
                headers=self._get_headers(is_api=True, referer=referer)
            )
            
            if response.ok:
                data = response.json()
                
                # 保存到文件
                self._write_to_file(file_path, data)
                
                # 处理笔记列表
                reviews = data.get("reviews", [])
                reviews = list(map(lambda x: x.get("review"), reviews))
                reviews = [
                    {"chapterUid": 1000000, **x} if x.get("type") == 4 else x
                    for x in reviews
                ]
                
                logger.info(f"成功从API获取书籍 {bookId} 的笔记列表，共 {len(reviews)} 条笔记")
                return reviews
            else:
                logger.error(f"获取书籍 {bookId} 的笔记列表失败: HTTP {response.status_code}")
                return []
        except Exception as e:
            print(f"DEBUG: 请求异常: {str(e)}")
            raise

    # 已经将 handle_errcode 方法重构为 _handle_error_code 方法

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_chapter_info(self, bookId: str) -> Dict[str, Dict]:
        """获取书籍的章节信息
        
        首先尝试从本地文件读取，如果文件不存在或读取失败，则从API获取。
        
        Args:
            bookId: 书籍ID
            
        Returns:
            Dict[str, Dict]: 章节信息字典，以chapterUid为键
        """
        # 尝试从文件读取
        file_path = self.data_dir / "books" / f"{bookId}_chapters.json"
        data = self._read_from_file(file_path)
        
        if data and isinstance(data, dict) and "data" in data:
            # 处理章节信息
            chapters_info = data.get("data", [])
            if chapters_info:
                # 处理第一本书的章节信息
                book_info = chapters_info[0]
                chapters = book_info.get("updated", [])
                
                # 将章节信息转换为以chapterUid为键的字典
                chapter_dict = {}
                for chapter in chapters:
                    chapter_dict[str(chapter.get("chapterUid"))] = chapter
                
                # 添加点评章节
                chapter_dict["1000000"] = {
                    "chapterUid": 1000000,
                    "chapterIdx": 1000000,
                    "updateTime": int(time.time()),
                    "readAhead": 0,
                    "title": "点评",
                    "level": 1,
                }
                
                logger.info(f"成功从文件读取书籍 {bookId} 的章节信息，共 {len(chapter_dict)} 章")
                return chapter_dict
        
        # 从API获取
        logger.info(f"从API获取书籍 {bookId} 的章节信息")
        try:
            # 访问主页初始化会话
            self.session.get(WEREAD_URL, headers=self._get_headers(is_api=False))
            
            # 设置请求体
            body = {"bookIds":[bookId], "synckeys":[0], "teenmode":0}
            
            referer = f"https://weread.qq.com/web/reader/{bookId}"
            
            # 发送请求
            response = self._make_request(
                WEREAD_API["chapter_info"],
                method="post",
                data=body,
                headers=self._get_headers(is_api=True, referer=referer)
            )
            
            if response.ok:
                data = response.json()
                
                # 保存到文件
                self._write_to_file(file_path, data)
                
                # 处理章节信息
                chapters_info = data.get("data", [])
                if not chapters_info:
                    logger.warning(f"没有找到书籍 {bookId} 的章节信息")
                    return {}
                
                # 处理第一本书的章节信息
                book_info = chapters_info[0]
                chapters = book_info.get("updated", [])
                
                # 将章节信息转换为以chapterUid为键的字典
                chapter_dict = {}
                for chapter in chapters:
                    chapter_dict[str(chapter.get("chapterUid"))] = chapter
                
                # 添加点评章节
                chapter_dict["1000000"] = {
                    "chapterUid": 1000000,
                    "chapterIdx": 1000000,
                    "updateTime": int(time.time()),
                    "readAhead": 0,
                    "title": "点评",
                    "level": 1,
                }
                
                logger.info(f"成功获取书籍 {bookId} 的章节信息，共 {len(chapter_dict)} 章")
                return chapter_dict
            else:
                logger.error(f"获取书籍 {bookId} 的章节信息失败: HTTP {response.status_code}")
                return {}
        except Exception as e:
            logger.exception(f"获取书籍 {bookId} 的章节信息异常: {str(e)}")
            return {}

    def calculate_book_str_id(self, book_id):
        md5 = hashlib.md5()
        md5.update(book_id.encode("utf-8"))
        digest = md5.hexdigest()
        result = digest[0:3]
        code, transformed_ids = self.transform_id(book_id)
        result += code + "2" + digest[-2:]

        for i in range(len(transformed_ids)):
            hex_length_str = format(len(transformed_ids[i]), "x")
            if len(hex_length_str) == 1:
                hex_length_str = "0" + hex_length_str

            result += hex_length_str + transformed_ids[i]

            if i < len(transformed_ids) - 1:
                result += "g"

        if len(result) < 20:
            result += digest[0 : 20 - len(result)]

        md5 = hashlib.md5()
        md5.update(result.encode("utf-8"))
        result += md5.hexdigest()[0:3]
        return result

    def get_url(self, book_id):
        return f"https://weread.qq.com/web/reader/{self.calculate_book_str_id(book_id)}"
