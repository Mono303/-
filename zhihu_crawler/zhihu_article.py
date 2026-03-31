"""
知乎单篇文章爬取
用法：修改底部 ARTICLE_URL，运行 python zhihu_article.py
"""

import time
import re
import os
import json
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


# ─────────────────────────────────────────────
#  配置（只需修改这里）
# ─────────────────────────────────────────────
ARTICLE_URL = "填入你想爬的文章链接"  # 替换成你要爬的文章链接
OUTPUT_DIR  = "zhihu_output"


# ─────────────────────────────────────────────
#  工具
# ─────────────────────────────────────────────
def safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()[:80]


def html_to_markdown(html):
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
        if name == "a":   return f"[{inner}]({tag.get('href','')})"
        if name == "img": return f"![{tag.get('alt','图片')}]({tag.get('src','')})"
        if name == "blockquote": return f"\n> {inner}\n"
        if name == "code": return f"`{inner}`"
        if name == "pre":  return f"\n```\n{inner}\n```\n"
        if name == "br":   return "\n"
        if name == "ul":
            return "\n" + "\n".join(f"- {convert(li)}" for li in tag.find_all("li", recursive=False)) + "\n"
        if name == "ol":
            return "\n" + "\n".join(f"{i+1}. {convert(li)}" for i, li in enumerate(tag.find_all("li", recursive=False))) + "\n"
        return inner

    md = convert(soup)
    return re.sub(r'\n{3,}', '\n\n', md).strip()


# ─────────────────────────────────────────────
#  浏览器
# ─────────────────────────────────────────────
def create_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


def login(driver):
    driver.get("https://www.zhihu.com")
    time.sleep(2)
    cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
    if "z_c0" in cookies:
        print("✅ 已登录")
        return
    if os.path.exists("zhihu_cookie.txt"):
        with open("zhihu_cookie.txt", encoding="utf-8") as f:
            for part in f.read().strip().split(";"):
                if "=" in part:
                    name, _, value = part.strip().partition("=")
                    try:
                        driver.add_cookie({"name": name.strip(), "value": value.strip(), "domain": ".zhihu.com"})
                    except Exception:
                        pass
        driver.refresh()
        time.sleep(2)
        if "z_c0" in {c["name"]: c["value"] for c in driver.get_cookies()}:
            print("✅ Cookie 加载成功")
            return
    print("⚠️  请在浏览器窗口中登录知乎，登录后自动继续...")
    driver.get("https://www.zhihu.com/signin")
    while True:
        time.sleep(2)
        if "z_c0" in {c["name"] for c in driver.get_cookies()}:
            print("✅ 登录成功")
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in driver.get_cookies())
            open("zhihu_cookie.txt", "w", encoding="utf-8").write(cookie_str)
            break
        print("⏳ 等待登录...", end="\r")


# ─────────────────────────────────────────────
#  主流程
# ─────────────────────────────────────────────
def crawl_article(url):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    driver = create_driver()

    try:
        login(driver)

        print(f"📄 正在打开：{url}")
        driver.get(url)
        time.sleep(3)

        # 获取标题
        title = "未知标题"
        for sel in ["h1.Post-Title", "h1", ".Post-Title"]:
            try:
                title = driver.find_element("css selector", sel).text.strip()
                if title:
                    break
            except Exception:
                pass

        # 获取正文 HTML
        content_html = ""
        for sel in [".Post-RichTextContainer", ".RichText", ".Post-content"]:
            try:
                el = driver.find_element("css selector", sel)
                content_html = el.get_attribute("innerHTML")
                if content_html and len(content_html) > 50:
                    break
            except Exception:
                pass

        if not content_html:
            print("❌ 未能获取到正文，请检查链接或登录状态")
            return

        # 转换为 Markdown
        content_md = html_to_markdown(content_html)

        # 保存文件
        filename = safe_filename(title) + ".md"
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n> **原文**：{url}\n\n---\n\n{content_md}\n")

        print(f"✅ 保存成功：{filepath}")
        print(f"   标题：{title}")
        print(f"   正文长度：{len(content_md)} 字符")

    finally:
        driver.quit()


if __name__ == "__main__":
    crawl_article(ARTICLE_URL)
