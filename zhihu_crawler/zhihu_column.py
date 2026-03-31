"""
知乎专栏爬虫（Selenium 版）
- 用真实浏览器请求，完全绕过反爬
- 自动登录，自动翻页，保存为 JSON + Markdown
用法：
  pip install selenium beautifulsoup4
  python zhihu_crawler.py
"""

import time
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


# ─────────────────────────────────────────────
#  配置（只需修改这里）
# ─────────────────────────────────────────────
COLUMN_ID  = "填入你想爬的专栏id"   # 专栏 ID
OUTPUT_DIR = "zhihu_output"            # 输出目录
PAGE_SIZE  = 20                        # 每页文章数
DELAY      = 1.5                       # 请求间隔（秒）


# ─────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────
def safe_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()[:80]


def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    def convert(tag):
        if isinstance(tag, str):
            return tag
        name = tag.name
        inner = "".join(convert(c) for c in tag.children)
        if name == "h1": return f"\n# {inner}\n"
        if name == "h2": return f"\n## {inner}\n"
        if name == "h3": return f"\n### {inner}\n"
        if name == "p":  return f"\n{inner}\n"
        if name in ("strong", "b"): return f"**{inner}**"
        if name in ("em", "i"):     return f"*{inner}*"
        if name == "a":
            return f"[{inner}]({tag.get('href', '')})"
        if name == "img":
            return f"![{tag.get('alt','图片')}]({tag.get('src','')})"
        if name == "blockquote": return f"\n> {inner}\n"
        if name == "code":       return f"`{inner}`"
        if name == "pre":        return f"\n```\n{inner}\n```\n"
        if name == "br":         return "\n"
        if name == "ul":
            return "\n" + "\n".join(f"- {convert(li)}" for li in tag.find_all("li", recursive=False)) + "\n"
        if name == "ol":
            return "\n" + "\n".join(f"{i+1}. {convert(li)}" for i, li in enumerate(tag.find_all("li", recursive=False))) + "\n"
        return inner

    md = convert(soup)
    return re.sub(r'\n{3,}', '\n\n', md).strip()


# ─────────────────────────────────────────────
#  浏览器初始化
# ─────────────────────────────────────────────
def create_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


# ─────────────────────────────────────────────
#  登录
# ─────────────────────────────────────────────
def login(driver):
    driver.get("https://www.zhihu.com")
    time.sleep(3)

    # 检查是否已有 z_c0（已登录）
    cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
    if "z_c0" in cookies:
        print("✅ 已检测到登录状态")
        return

    # 尝试加载保存的 cookie
    if os.path.exists("zhihu_cookie.txt"):
        print("📂 发现 zhihu_cookie.txt，尝试加载...")
        with open("zhihu_cookie.txt", encoding="utf-8") as f:
            for part in f.read().strip().split(";"):
                part = part.strip()
                if "=" in part:
                    name, _, value = part.partition("=")
                    try:
                        driver.add_cookie({
                            "name": name.strip(),
                            "value": value.strip(),
                            "domain": ".zhihu.com"
                        })
                    except Exception:
                        pass
        driver.refresh()
        time.sleep(3)
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        if "z_c0" in cookies:
            print("✅ Cookie 加载成功")
            return

    # 需要手动登录
    print("=" * 50)
    print("⚠️  请在弹出的浏览器窗口中登录知乎")
    print("   支持扫码 / 账号密码 / 手机验证码")
    print("   登录成功后脚本自动继续...")
    print("=" * 50)
    driver.get("https://www.zhihu.com/signin")

    while True:
        time.sleep(2)
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        if "z_c0" in cookies:
            print("✅ 登录成功！")
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in driver.get_cookies())
            with open("zhihu_cookie.txt", "w", encoding="utf-8") as f:
                f.write(cookie_str)
            print("💾 Cookie 已保存到 zhihu_cookie.txt（下次无需重新登录）")
            break
        print("⏳ 等待登录...", end="\r")


# ─────────────────────────────────────────────
#  用浏览器内置 fetch 调用 API（绕过反爬）
# ─────────────────────────────────────────────
def fetch_json(driver, url):
    result = driver.execute_async_script("""
        var url = arguments[0];
        var callback = arguments[1];
        fetch(url, {
            credentials: "include",
            headers: {"Accept": "application/json, text/plain, */*"}
        })
        .then(r => r.text())
        .then(t => callback(t))
        .catch(e => callback("__ERROR__" + e.toString()));
    """, url)

    if result.startswith("__ERROR__"):
        raise Exception(result[9:])
    return json.loads(result)


# ─────────────────────────────────────────────
#  爬取逻辑
# ─────────────────────────────────────────────
def get_column_articles(driver, column_id):
    all_articles = []
    offset = 0
    print(f"📥 开始获取专栏文章列表（专栏 ID: {column_id}）")

    while True:
        url = (f"https://www.zhihu.com/api/v4/columns/{column_id}/items"
               f"?limit={PAGE_SIZE}&offset={offset}")
        try:
            data = fetch_json(driver, url)
        except Exception as e:
            print(f"  ⚠️  请求失败（offset={offset}）: {e}")
            break

        items = data.get("data", [])
        if not items:
            break

        for item in items:
            if item.get("type") != "article":
                continue
            all_articles.append({
                "id":            item.get("id"),
                "title":         item.get("title", "无标题"),
                "url":           item.get("url", ""),
                "created_at":    item.get("created", 0),
                "excerpt":       BeautifulSoup(item.get("excerpt", ""), "html.parser").get_text(),
                "voteup_count":  item.get("voteup_count", 0),
                "comment_count": item.get("comment_count", 0),
                "author":        item.get("author", {}).get("name", "未知"),
            })

        print(f"  已获取 {len(all_articles)} 篇（offset={offset}）")

        if data.get("paging", {}).get("is_end", True):
            break

        offset += PAGE_SIZE
        time.sleep(DELAY)

    print(f"✅ 共获取到 {len(all_articles)} 篇文章\n")
    return all_articles


def get_article_content(driver, article):
    """先尝试 API，API 正文为空时直接打开页面抓取 DOM"""
    # 方法1：API
    try:
        url = f"https://www.zhihu.com/api/v4/articles/{article['id']}"
        data = fetch_json(driver, url)
        html = data.get("content", "")
        if html and len(html) > 50:
            return html
    except Exception:
        pass

    # 方法2：直接访问文章页面抓取正文
    article_url = article.get("url", f"https://zhuanlan.zhihu.com/p/{article['id']}")
    driver.get(article_url)
    time.sleep(2)
    for _ in range(10):
        try:
            el = driver.find_element("css selector", ".Post-RichTextContainer, .RichText")
            html = el.get_attribute("innerHTML")
            if html and len(html) > 50:
                return html
        except Exception:
            pass
        time.sleep(1)
    return ""


# ─────────────────────────────────────────────
#  保存
# ─────────────────────────────────────────────
def save_markdown(article, output_dir):
    md_dir = os.path.join(output_dir, "markdown")
    os.makedirs(md_dir, exist_ok=True)
    created = datetime.fromtimestamp(article.get("created_at", 0)).strftime("%Y-%m-%d")
    md = f"""# {article['title']}

> **作者**：{article.get('author','未知')}　｜　**日期**：{created}　｜　**赞同**：{article.get('voteup_count',0)}
> **原文**：{article.get('url','')}

---

{article.get('content_md', '')}
"""
    path = os.path.join(md_dir, f"{safe_filename(article['title'])}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)


# ─────────────────────────────────────────────
#  主流程
# ─────────────────────────────────────────────
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    driver = create_driver()

    try:
        # 1. 登录
        login(driver)

        # 2. 停留在知乎主页（保证 fetch 的 origin 正确）
        driver.get("https://www.zhihu.com")
        time.sleep(2)

        # 3. 获取文章列表
        articles = get_column_articles(driver, COLUMN_ID)
        if not articles:
            print("❌ 未获取到任何文章，请检查专栏 ID")
            return

        # 4. 获取正文
        print("📄 开始下载文章正文...")
        for i, article in enumerate(articles):
            print(f"  [{i+1}/{len(articles)}] {article['title'][:50]}")
            try:
                html = get_article_content(driver, article)
                article["content_md"] = html_to_markdown(html)
                save_markdown(article, OUTPUT_DIR)
                # 回到主页保证下次 fetch origin 正确
                driver.get("https://www.zhihu.com")
                time.sleep(1)
            except Exception as e:
                print(f"    ⚠️  失败: {e}")
                article["content_md"] = ""
            time.sleep(DELAY)

        # 5. 保存 JSON
        json_path = os.path.join(OUTPUT_DIR, "articles.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)

        print(f"\n🎉 完成！共爬取 {len(articles)} 篇文章")
        print(f"   Markdown 文件：{OUTPUT_DIR}/markdown/")
        print(f"   JSON 汇总：{json_path}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
