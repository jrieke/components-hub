import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pyppeteer
import requests
import streamlit as st
from bs4 import BeautifulSoup
from st_keyup import st_keyup
from stqdm import stqdm

st.set_page_config("Streamlit Components Hub", "🧩", layout="wide")
NUM_COLS = 4

EXCLUDE = [
    "streamlit",
    "streamlit-nightly",
    "streamlit-fesion",
    "streamlit-aggrid-pro",
    "st-dbscan",
    "st-kickoff",
    "st-undetected-chromedriver",
    "st-package-reviewer",
]


def icon(emoji: str):
    """Shows an emoji as a Notion-style page icon."""
    st.write(
        f'<span style="font-size: 78px; line-height: 1">{emoji}</span>',
        unsafe_allow_html=True,
    )


st.write(
    '<style>[data-testid="stImage"] img {border: 1px solid #D6D6D9; border-radius: 3px; height: 200px; object-fit: cover; width: 100%} .block-container img:hover {}</style>',
    unsafe_allow_html=True,
)

# st.write(
#     "<style>.block-container img {border: 1px solid #D6D6D9; border-radius: 3px; width: 100%; height: 200px; position: absolute; top: 50%; left: 50%;transform: translate(-50%, -50%);} .block-container img:hover {}</style>",
#     unsafe_allow_html=True,
# )

icon("🧩")
"""
# Streamlit Components Hub
"""
description = st.empty()
col1, col2 = st.columns([2, 1])
# with col1:
search = st_keyup("Search", debounce=50)
# with col2:
#     st.selectbox("Sort by", ["Github stars", "Newest"], disabled=True)
st.write("")
st.write("")


@st.experimental_memo(ttl=24 * 3600, persist="disk", show_spinner=False)
def get(*args, **kwargs):
    res = requests.get(*args, **kwargs)
    return res.status_code, res.text


@st.experimental_memo(ttl=24 * 3600, persist="disk", show_spinner=False)
def get_stars_and_description(url):
    """use the github api to get the number of stars for a given repo"""
    url = url.replace("https://", "").replace("http://", "")
    user, repo = url.split("/")[1:3]
    response = requests.get(
        f"https://api.github.com/repos/{user}/{repo}",
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Token {st.secrets.gh_token}",
        },
    )
    if response.status_code == 404:
        return None, None, None
    elif response.status_code != 200:
        raise RuntimeError(
            f"Couldn't get repo details, status code {response.status_code} for url: {url}, user: {user}, repo: {repo}"
        )
    response_json = response.json()
    return (
        response_json["stargazers_count"],
        response_json["description"],
        response_json["owner"]["avatar_url"],
    )


@st.experimental_memo(ttl=24 * 3600, persist="disk", show_spinner=False)
def parse_github_readme(url):
    """get the image url from the github readme"""
    status_code, text = get(url)
    if status_code == 404:
        return None, None
    elif status_code != 200:
        raise RuntimeError(
            f"Couldn't get Github page, status code {status_code} for url: {url}"
        )
    time.sleep(0.2)  # wait a bit to not get rate limited
    soup = BeautifulSoup(text, "html.parser")
    # st.expander("Show HTML").code(response.text)
    readme = soup.find(id="readme")
    if readme is None:
        return None, None

    # Find first image that's not a badge or logo.
    images = readme.find_all("img")

    def is_no_badge(img):
        srcs = img["src"] + img.get("data-canonical-src", "")
        return not (
            "badge" in srcs
            or "shields.io" in srcs
            or "circleci" in srcs
            or "buymeacoffee" in srcs
            or "ko-fi" in srcs
            or "logo" in srcs
        )

    images = list(filter(is_no_badge, images))
    if not images:
        image_url = None
    else:
        image_url = images[0]["src"]
        if image_url.startswith("/"):
            image_url = "https://github.com" + image_url

    # Find text in first paragraph.
    description = None
    paragraphs = readme.find_all("p")
    for p in paragraphs:
        text = p.text.strip()
        if text:
            description = text.replace("\n", "")
            break

    # print("func", image_url, description)
    return image_url, description


async def _save_screenshot(
    url: str, img_path: str, sleep: int = 5, width: int = 1024, height: int = 576
) -> None:
    browser = await pyppeteer.launch(
        {"args": ["--no-sandbox"]},
        handleSIGINT=False,
        handleSIGTERM=False,
        handleSIGHUP=False,
    )
    page = await browser.newPage()
    await page.goto(url, {"timeout": 6000})  # increase timeout to 60 s for heroku apps
    await page.emulate({"viewport": {"width": width, "height": height}})
    time.sleep(sleep)
    # Type (PNG or JPEG) will be inferred from file ending.
    await page.screenshot({"path": img_path})
    await browser.close()


def save_screenshot(
    url: str, img_path: str, sleep: int = 5, width: int = 1024, height: int = 576
):
    asyncio.run(
        _save_screenshot(
            url=url, img_path=img_path, sleep=sleep, width=width, height=height
        )
    )


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


TRACKER = "https://discuss.streamlit.io/t/streamlit-components-community-tracker/4634"


@dataclass
class Component:
    name: str = None
    package: str = None
    demo: str = None
    forum_post: str = None
    github: str = None
    pypi: str = None
    image_url: str = None
    # screenshot_url: str = None
    stars: int = None
    github_description: str = None
    avatar: str = None
    search_text: str = None
    github_author: str = None
    pypi_author: str = None


@st.experimental_memo
def get_all_packages():
    url = "https://pypi.org/simple/"
    status_code, text = get(url)
    soup = BeautifulSoup(text, "html.parser")
    packages = [a.text for a in soup.find_all("a")]
    return packages


@st.experimental_memo(ttl=3600, show_spinner=False)
def get_components():
    components = {}

    # Step 1: Get components from tracker
    status_code, text = get(TRACKER)
    if status_code != 200:
        raise RuntimeError(
            f"Could not access components tracker, status code {status_code}"
        )

    soup = BeautifulSoup(text, "html.parser")
    lis = soup.find_all("ul")[3].find_all("li")

    for li in stqdm(lis, desc="🔍 Crawling components"):

        c = Component()
        name = re.sub("\(.*?\)", "", li.text)
        name = name.split(" – ")[0]
        c.name = name

        links = [a.get("href") for a in li.find_all("a")]
        for l in links:
            if l.startswith("https://github.com"):
                c.github = l
            elif l.startswith("https://share.streamlit.io") or "streamlitapp.com" in l:
                c.demo = l
            elif l.startswith("https://discuss.streamlit.io"):
                c.forum_post = l
            elif l.startswith("https://pypi.org"):
                c.pypi = l
                c.package = re.match("https://pypi.org/project/(.*?)/", l).group(1)

        if c.github and not c.package:
            repo_name = (
                c.github.replace("https://", "").replace("http://", "").split("/")[2]
            )
            # print(repo_name)
            url = f"https://pypi.org/project/{repo_name}/"
            status_code, text = get(url)
            if status_code != 404:
                c.package = repo_name
                c.pypi = url
                # print("found package based on repo name:", repo_name)

        if c.package:
            components[c.package] = c
        else:
            components[c.name] = c

    # Step 2: Get components from PyPI
    packages = get_all_packages()

    with st.spinner("Parsing PyPI packages"):
        for p in packages:
            if p.startswith("streamlit") or p.startswith("st-") or p.startswith("st_"):
                url = f"https://pypi.org/project/{p}/"
                status_code, text = get(url)
                if status_code != 404:
                    # st.expander("show html").code(res.text)

                    if not p in components:
                        components[p] = Component(name=p)
                    c = components[p]

                    if not c.package:
                        c.package = p
                    if not c.pypi:
                        c.pypi = url

                    if not c.pypi_author or not c.github:
                        soup = BeautifulSoup(text, "html.parser")

                        if not c.pypi_author:
                            pypi_author = soup.find(
                                "span", class_="sidebar-section__user-gravatar-text"
                            ).text.strip()
                            c.pypi_author = pypi_author

                        if not c.github:
                            homepage = soup.find("i", class_="fas fa-home")
                            if homepage and "github.com" in homepage.parent["href"]:
                                c.github = homepage.parent["href"]
                                print("found github link from homepage link:", c.github)
                            else:
                                sidebar_links = soup.find_all(
                                    "a",
                                    class_="vertical-tabs__tab vertical-tabs__tab--with-icon vertical-tabs__tab--condensed",
                                )
                                for l in sidebar_links:
                                    if "github.com" in l["href"]:
                                        c.github = l["href"]
                                        print(
                                            "found github link from sidebar link:",
                                            c.github,
                                        )
                                        break
                        
                        

    # TODO: Could also find github + demo app + package name in the blog post or on github is nothing else is given.
    # At least getting demo app from github should be very easy, either from URL field or from readme text.
    # Package name might also be easy but should check that there's at least some overlap to repo name, to make sure this isn't another package.

    # Step 3: Enrich info of components found above
    for c in stqdm(components.values(), desc="🔍 Enriching component info"):

        # Try to get Github URL by combining PyPI author name + package name.
        if c.github is None and c.package and c.pypi_author:
            status_code, text = get(
                f"https://api.github.com/repos/{c.pypi_author}/{c.package}",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": f"Token {st.secrets.gh_token}",
                },
            )
            if status_code == 200:
                c.github = f"https://github.com/{c.pypi_author}/{c.package}"
                # print(
                #     "found github page by combining pypi author + package name:",
                #     c.github,
                # )

        # st.write(c)
        if c.github is not None:
            # print(c.github)
            c.github_author = re.search("github.com/(.*?)/", c.github).group(1)
            c.stars, c.github_description, c.avatar = get_stars_and_description(
                c.github
            )

            c.image_url, readme_description = parse_github_readme(c.github)  # this can also return None!
            if not c.github_description:
                print("found description from github readme")
                c.github_description = readme_description

        # TODO: Can get rid of this by just looking below if image_url is set,
        # and if not, screenshot the demo url.
        # if c.image_url is None and c.demo is not None:
        #     c.screenshot_url = c.demo

        c.search_text = (
            str(c.name)
            + str(c.github_description)
            + str(c.github_author)
            + str(c.package)
        )

    # Exclude some manually defined components
    for name in EXCLUDE:

        try:
            del components[name]
        except KeyError:
            pass

    # Sort by Github stars
    components_list = sorted(
        components.values(),
        key=lambda c: (
            c.stars if c.stars is not None else 0,
            c.image_url is not None,  # items with image first
        ),
        reverse=True,
    )
    return components_list


# @st.experimental_memo
def show_components(components, search):
    if search:
        components_to_show = list(
            filter(lambda c: search.lower() in c.search_text, components)
        )
    else:
        components_to_show = components

    for components_chunk in chunks(components_to_show, NUM_COLS):
        cols = st.columns(NUM_COLS, gap="medium")
        for c, col in zip(components_chunk, cols):
            with col:
                if c.image_url is not None:
                    img_path = c.image_url
                # TODO: This doesn't work on Cloud, disabling for now.
                # elif c.demo is not None:
                #     screenshot_dir = Path("screenshots")
                #     screenshot_dir.mkdir(exist_ok=True, parents=True)
                #     escaped_screenshot_url = (
                #         c.demo.replace("https://", "")
                #         .replace("/", "_")
                #         .replace(".", "_")
                #     )
                #     img_path = screenshot_dir / f"{escaped_screenshot_url}.png"
                #     if not img_path.exists():
                #         save_screenshot(c.demo, img_path, sleep=15)
                else:
                    img_path = "default_image.png"

                st.image(str(img_path), use_column_width=True)
                title = f"#### {c.name}"
                if c.stars:
                    title += f" ({c.stars} ⭐️)"
                st.write(title)
                if c.github_author and c.avatar:
                    st.caption(
                        f'<a href="https://github.com/{c.github_author}"><img src="{c.avatar}" style="border: 1px solid #D6D6D9; width: 20px; height: 20px; border-radius: 50%"></a> &nbsp; <a href="https://github.com/{c.github_author}" style="color: inherit; text-decoration: inherit">{c.github_author}</a>',
                        unsafe_allow_html=True,
                    )
                elif c.github_author:
                    # TODO: Some of the Github pages extracted above return 404, so
                    # we can't get the avatar image from them. We could get them by
                    # querying with the author name directly but for now I'm just hiding the avatar images.
                    st.caption(
                        f'<a href="https://github.com/{c.github_author}" style="color: inherit; text-decoration: inherit">{c.github_author}</a>',
                        unsafe_allow_html=True,
                    )
                elif c.pypi_author:
                    st.caption(
                        f'<a href="https://pypi.org/user/{c.pypi_author}" style="color: inherit; text-decoration: inherit">{c.pypi_author}</a>',
                        unsafe_allow_html=True,
                    )

                if c.github_description is not None:
                    st.write(c.github_description)
                if c.package is not None:
                    st.code(f"pip install {c.package}")
                formatted_links = []
                if c.github is not None:
                    formatted_links.append(f"[GitHub]({c.github})")
                if c.demo is not None:
                    formatted_links.append(f"[Demo]({c.demo})")
                if c.forum_post is not None:
                    formatted_links.append(f"[Forum]({c.forum_post})")
                if c.pypi is not None:
                    formatted_links.append(f"[PyPI]({c.pypi})")

                st.write(" • ".join(formatted_links))
        st.write("---")


components = get_components()
description.write(
    f"""
Discover {len(components)} Streamlit components!
All components are automatically crawled from [PyPI](https://pypi.org/) and the
[forum](https://discuss.streamlit.io/t/streamlit-components-community-tracker/4634).
The metadata is coming from Github.
"""
)
show_components(components, search)
