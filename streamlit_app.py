import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

import httpx
import pypistats
import requests
import streamlit as st
import yaml
from bs4 import BeautifulSoup
from markdownlit import mdlit
from stqdm import stqdm

# from streamlit_dimensions import st_dimensions
from streamlit_pills import pills

# from streamlit_profiler import Profiler

# profiler = Profiler()

st.set_page_config("Streamlit Components Hub", "🎪", layout="wide")
NUM_COLS = 4

EXCLUDE = [
    "streamlit",
    "streamlit-nightly",
    "repl-streamlit",
    "streamlit-with-ssl",
    "streamlit-fesion",
    "streamlit-aggrid-pro",
    "st-dbscan",
    "st-kickoff",
    "st-undetected-chromedriver",
    "st-package-reviewer",
    "streamlit-webcam-example",
    "st-pyv8",
    "streamlit-extras-arnaudmiribel",
    "st-schema-python",
    "st-optics",
    "st-spin",
    "st-dataprovider",
    "st-microservice",
    "st_nester",
    "st-jsme",
    "st-parsetree",
    "st-git-hooks",
    "st-schema",
    "st-distributions",
    "st-common-data",
    "awesome-streamlit",
    "awesome-streamlit-master",
    "extra-streamlit-components-SEM",
    "barfi",
    "streamlit-plotly-events-retro",
    "pollination-streamlit-io",
    "pollination-streamlit-viewer",
    "st-clustering",
    "streamlit-text-rating-component",
]

CATEGORY_NAMES = {
    # Putting this first so people don't miss it. Plus I think's it's one of the most
    # important ones.
    "widgets": "General widgets",  # 35
    # Visualizations of different data types.
    "charts": "Charts",  # 16
    "image": "Images",  # 10
    "video": "Video",  # 6
    "text": "Text",  # 12
    "maps": "Maps & geospatial",  # 7
    "dataframe": "Dataframes & tables",  # 6
    "science": "Molecules & genes",  # 3
    "graph": "Graphs",  # 7
    "3d": "3D",  # 1
    "code": "Code & editors",  # 4
    # More general elements in the app.
    "navigation": "Page navigation",  # 12
    "authentication": "Authentication",  # 5
    "style": "Style & layout",  # 3
    # More backend-y/dev stuff.
    # TODO: Should probably split this up, "Developer tools" contains a lot of stuff.
    "development": "Developer tools",  # 22
    "app-builder": "App builders",  # 3
    # General purpose categories.
    "integrations": "Integrations with other tools",  # 14
    "collection": "Collections of components",  # 4
}

CATEGORY_ICONS = [
    "🧰",
    "📊",
    "🌇",
    "🎥",
    "📝",
    "🗺️",
    "🧮",
    "🧬",
    "🪢",
    "🧊",
    "✏️",
    "📃",
    "🔐",
    "🎨",
    "🛠️",
    "🏗️",
    "🔌",
    "📦",
]


def icon(emoji: str):
    """Shows an emoji as a Notion-style page icon."""
    st.write(
        f'<span style="font-size: 78px; line-height: 1">{emoji}</span>',
        unsafe_allow_html=True,
    )


st.write(
    '<style>button[title="View fullscreen"], h4 a {display: none !important} [data-testid="stImage"] img {border: 1px solid #D6D6D9; border-radius: 3px; height: 200px; object-fit: cover; width: 100%} .block-container img:hover {}</style>',
    unsafe_allow_html=True,
)

# Only do this once at the beginning of the session. If we're doing it at every rerun,
# the width will fluctuate because the sidebar appears or disappears, leading to
# this running over and over again.
# Note that this slows the app down quite a bit because it triggers a second rerun,
# as soon as st_dimensions knows its width.
# if "screen_width" not in st.session_state:
#     dimensions = st_dimensions()
#     if dimensions is not None:
#         st.session_state.screen_width = dimensions["width"]

# if "screen_width" in st.session_state and st.session_state.screen_width < 768:
#     container = st.container()  # small screen, show controls at top of page
# else:
#     container = st.sidebar  # large screen, show controls in sidebar

# with container:
icon("🎪")
"""
# Streamlit Components Hub

[![](https://img.shields.io/github/stars/jrieke/components-hub?style=social)](https://github.com/jrieke/components-hub) &nbsp; [![](https://img.shields.io/twitter/follow/jrieke?style=social)](https://twitter.com/jrieke)
"""

description_text = """
Discover {} Streamlit components! Most information on this page is 
automatically crawled from Github, PyPI, and the 
[Streamlit forum](https://discuss.streamlit.io/t/streamlit-components-community-tracker/4634).
If you build your own [custom component](https://docs.streamlit.io/library/components/create), 
it should appear here within a few days.
"""
description = st.empty()
description.write(description_text.format("all"))
col1, col2 = st.columns([2, 1])
search = col1.text_input("Search", placeholder='e.g. "image" or "text" or "card"')
sorting = col2.selectbox(
    "Sort by", ["⭐️ Stars on GitHub", "⬇️ Downloads last month", "🐣 Newest"]
)
install_command = "pip install"
category = pills(
    "Category",
    list(CATEGORY_NAMES.keys()),
    CATEGORY_ICONS,
    index=None,
    format_func=lambda x: CATEGORY_NAMES.get(x, x),
    label_visibility="collapsed",
)

# if "screen_width" in st.session_state and st.session_state.screen_width < 768:
st.write("")


@st.experimental_memo(ttl=28 * 24 * 3600, persist="disk", show_spinner=False)
def get(*args, **kwargs):
    res = requests.get(*args, **kwargs)
    return res.status_code, res.text


@st.experimental_memo(ttl=28 * 24 * 3600, persist="disk", show_spinner=False)
def get_github_info(url):
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
        return None, None, None, None
    elif response.status_code != 200:
        raise RuntimeError(
            f"Couldn't get repo details, status code {response.status_code} for url: {url}, user: {user}, repo: {repo}"
        )
    response_json = response.json()
    created_at = datetime.strptime(response_json["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    return (
        response_json["stargazers_count"],
        response_json["description"],
        response_json["owner"]["avatar_url"],
        created_at,
    )


@st.experimental_memo(ttl=28 * 24 * 3600, persist="disk", show_spinner=False)
def parse_github_readme(url):
    """get the image url from the github readme"""
    # TODO: Could do this by getting the raw readme file and not the rendered page.
    # But then it's a lot more difficult to find images, since we need to parse markdown.
    status_code, text = get(
        url,
        headers={
            "Authorization": f"Token {st.secrets.gh_token}",
        },
    )
    if status_code == 404:
        return None, None, None
    elif status_code != 200:
        raise RuntimeError(
            f"Couldn't get Github page, status code {status_code} for url: {url}"
        )
    time.sleep(0.2)  # wait a bit to not get rate limited
    soup = BeautifulSoup(text, "html.parser")
    # st.expander("Show HTML").code(response.text)
    readme = soup.find(id="readme")
    if readme is None:
        return None, None, None

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
            or "streamlit-mark" in srcs
            or "coverage" in srcs
            or "Cover" in srcs
            or "hydra.png" in srcs
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
    for paragraph in paragraphs:
        clean_paragraph = paragraph.text.replace("\n", "").strip()
        if clean_paragraph:
            description = clean_paragraph
            break

    # Find link to demo app.
    # TODO: Should only do this if demo app is not known yet.
    try:
        demo_url = soup.find("a", href=re.compile("share\.streamlit\.io/+"))["href"]
    except TypeError:
        try:
            demo_url = soup.find("a", href=re.compile("\.streamlitapp\.com"))["href"]
        except TypeError:
            demo_url = None
            # TODO: Need to add streamlit.app here.

    # print("func", image_url, description)
    return image_url, description, demo_url


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
    pypi_description: str = None
    avatar: str = None
    search_text: str = None
    github_author: str = None
    pypi_author: str = None
    created_at: datetime = None
    downloads: int = None
    categories: List[str] = None


@st.experimental_memo(ttl=28 * 24 * 3600, persist="disk", show_spinner=False)
def get_all_packages():
    url = "https://pypi.org/simple/"
    status_code, text = get(url)
    soup = BeautifulSoup(text, "html.parser")
    packages = [
        a.text
        for a in soup.find_all("a")
        if (
            "streamlit" in a.text
            or a.text.startswith("st-")
            or a.text.startswith("st_")
        )
        and a.text not in EXCLUDE
    ]
    return packages


@st.experimental_memo(ttl=24 * 3600, persist="disk", show_spinner=False)
def get_downloads(package):
    try:
        downloads = pypistats.recent(package, "month", format="pandas")["last_month"][
            0
        ]  # .iloc[-1]["downloads"]
    except httpx.HTTPStatusError:
        time.sleep(10)
        try:
            downloads = pypistats.recent(package, "month", format="pandas")[
                "last_month"
            ][
                0
            ]  # .iloc[-1]["downloads"]
        except httpx.HTTPStatusError:
            # give up
            return 0
    time.sleep(0.1)  # don't get rate-limited
    return downloads


@st.experimental_memo(ttl=28 * 24 * 3600, show_spinner=False)
def get_components():
    components_dict = {}

    # Step 1: Get components from tracker
    status_code, text = get(TRACKER)
    if status_code != 200:
        raise RuntimeError(
            f"Could not access components tracker, status code {status_code}"
        )

    soup = BeautifulSoup(text, "html.parser")
    lis = soup.find_all("ul")[3].find_all("li")

    for li in stqdm(lis, desc="🎈 Crawling Streamlit forum (step 1/5)"):

        c = Component()
        name = re.sub("\(.*?\)", "", li.text)
        name = name.split(" – ")[0]
        name = name.strip()
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
            components_dict[c.package] = c
        else:
            components_dict[c.name] = c

    # Step 2: Download PyPI index
    with st.spinner("⬇️ Downloading PyPI index (step 2/5)"):
        packages = get_all_packages()

    # Step 3: Search through PyPI packages
    # TODO: This could be wrapped in memo as well.
    for p in stqdm(packages, desc="📦 Crawling PyPI (step 3/5)"):
        # if p.startswith("streamlit") or p.startswith("st-") or p.startswith("st_"):

        # TODO: There's a JSON API to do this: https://pypi.org/pypi/<package>/json

        url = f"https://pypi.org/project/{p}/"
        status_code, text = get(url)
        if status_code != 404:
            # st.expander("show html").code(res.text)

            if not p in components_dict:
                components_dict[p] = Component(name=p)
            c = components_dict[p]

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
                        # print("found github link from homepage link:", c.github)
                    else:
                        sidebar_links = soup.find_all(
                            "a",
                            class_="vertical-tabs__tab vertical-tabs__tab--with-icon vertical-tabs__tab--condensed",
                        )
                        for l in sidebar_links:
                            if "github.com" in l["href"]:
                                c.github = l["href"]
                                # print(
                                #     "found github link from sidebar link:",
                                #     c.github,
                                # )
                                break

                # TODO: Maybe do this outside of the if?
                summary = soup.find("p", class_="package-description__summary")
                if (
                    summary
                    and summary.text
                    and summary.text != "No project description provided"
                ):
                    # print("found summary description on pypi:", summary.text)
                    c.pypi_description = summary.text
                else:
                    # Search for first non-empty paragraph.
                    project_description = soup.find("div", class_="project-description")
                    if project_description:
                        paragraphs = project_description.find_all("p")
                        for p in paragraphs:
                            text = p.text.replace("\n", "").strip()
                            if text:
                                c.pypi_description = text
                                break

    # profiler.start()
    # Step 4: Enrich info of components found above by reading data from Github
    for c in stqdm(components_dict.values(), desc="👾 Crawling Github (step 4/5)"):

        # Try to get Github URL by combining PyPI author name + package name.
        if not c.github and c.package and c.pypi_author:
            possible_repo_names = [c.package]
            if "-" in c.package:
                # Sometimes, package names contain "-"" but repos "_", so check for these
                # mutations as well.
                possible_repo_names.append(c.package.replace("-", "_"))
            for repo in possible_repo_names:
                status_code, text = get(
                    f"https://api.github.com/repos/{c.pypi_author}/{repo}",
                    headers={
                        "Accept": "application/vnd.github.v3+json",
                        "Authorization": f"Token {st.secrets.gh_token}",
                    },
                )
                if status_code == 200:
                    c.github = f"https://github.com/{c.pypi_author}/{repo}"
                    if repo != c.package:
                        print(
                            f"found github url by mutating package name, original: {c.package}, mutated: {repo}"
                        )
                    break

        if c.github:
            # print(c.github)
            c.github_author = re.search("github.com/(.*?)/", c.github).group(1)
            try:
                (
                    c.stars,
                    c.github_description,
                    c.avatar,
                    c.created_at,
                ) = get_github_info(c.github)
            except:
                pass  # TODO: Handle this better. Sometimes Github shows 401 errors.

            # this can also return None!
            c.image_url, readme_description, demo_url = parse_github_readme(c.github)
            if not c.github_description and readme_description:
                # print("found description in github readme")
                c.github_description = readme_description
            if not c.demo and demo_url:
                # print("found demo url in github readme", demo_url)
                c.demo = demo_url

        # Get download numbers from PyPI
        if c.package:
            c.downloads = get_downloads(c.package)

        # Set names based on PyPI package names.
        # TODO: If I go with this, I should not even fetch the names from the forum post
        # above.
        if c.package:
            name = c.package
            if name.startswith("st-") or name.startswith("st_"):  # only do at start
                name = name[3:]
            c.name = (
                name.replace("streamlit", "")
                .replace("--", " ")
                .replace("-", " ")
                .replace("__", " ")
                .replace("_", " ")
                .strip()
                .title()
                .replace("Nlu", "NLU")  # special case adjustments for top results ;)
                .replace(" Cli", " CLI")
                .replace("rtc", "RTC")
                .replace("Hiplot", "HiPlot")
                .replace("Spacy", "SpaCy")
                .replace("Aggrid", "AgGrid")
                .replace("Echarts", "ECharts")
                .replace("Ui", "UI")
            )

            # if c.package.startswith("streamlit-"):
            #     c.name = c.package[10:].replace("-", " ").capitalize()
            # elif c.package.endswith("-streamlit"):
            #     c.name = c.package[:-10].replace("-", " ").capitalize()
            # elif c.package.startswith("st-"):
            #     c.name = c.package[3:].replace("-", " ").capitalize()
            # else:
            #     c.name = c.package.replace("-streamlit-", " ").replace("-", " ").capitalize()

        c.search_text = (
            str(c.name)
            + str(c.github_description)
            + str(c.pypi_description)
            + str(c.github_author)
            + str(c.package)
        )

    # profiler.stop()

    # Step 5: Enrich with additional data that was manually curated in
    # additional_data.yaml (currently only categories).
    with open("additional_data.yaml") as f:
        additional_data = yaml.safe_load(f)
    for c in stqdm(
        components_dict.values(),
        desc="🖐 Enriching with manually collected data (step 5/5)",
    ):
        # TODO: Need to do this better. Maybe just store pypi name instead of entire url.
        if c.pypi and c.pypi.split("/")[-2] in additional_data:
            c.categories = additional_data[c.pypi.split("/")[-2]]["categories"]
        else:
            c.categories = []
    return list(components_dict.values())


@st.experimental_memo(show_spinner=False)
def sort_components(components: list, by):
    if by == "⭐️ Stars on GitHub":
        return sorted(
            components,
            key=lambda c: (
                c.stars if c.stars is not None else 0,
                c.image_url is not None,  # items with image first
            ),
            reverse=True,
        )
    elif by == "🐣 Newest":
        # TODO: This only works for components that have a Github link because we pull
        # the created_at date from Github. Make this work with the release date on PyPI.
        return sorted(
            components,
            key=lambda c: (
                c.created_at if c.created_at is not None else datetime(1970, 1, 1),
                c.image_url is not None,  # items with image first
            ),
            reverse=True,
        )
    elif by == "⬇️ Downloads last month":
        return sorted(
            components,
            key=lambda c: (
                c.downloads if c.downloads is not None else 0,
                c.image_url is not None,  # items with image first
            ),
            reverse=True,
        )
    else:
        raise ValueError("`by` must be either 'Stars' or 'Newest'")


@st.experimental_memo(show_spinner=False)
def filter_components(components, search=None, category=None, newer_than=None):
    if search:
        components = list(filter(lambda c: search.lower() in c.search_text, components))
    if category:
        components = list(filter(lambda c: category in c.categories, components))
    if newer_than:
        components = list(
            filter(lambda c: c.created_at and c.created_at >= newer_than, components)
        )
    return components


def shorten(text, length=100):
    if len(text) > length:
        short_text = text[:length]

        # Cut last word if short_text doesn't end on a word.
        if short_text[-1] != " " and text[length] != " ":
            short_text = short_text[: short_text.rfind(" ")]

        # Remove whitespace at the end.
        short_text = short_text.rstrip()

        # Deal with sentence end markers.
        if short_text[-1] in [".", "!", "?"]:
            return short_text
        elif short_text[-1] in [",", ";", ":", "-"]:
            return short_text[:-1] + "..."
        else:
            return short_text + "..."
    else:
        return text


# Can't memo-ize this right now because st.image doesn't work.
# @st.experimental_memo
def show_components(components, limit=None):

    if limit is not None:
        components = components[:limit]

    for i, components_chunk in enumerate(chunks(components, NUM_COLS)):
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
                # print(title)
                st.write(title)
                if c.avatar:
                    avatar_path = c.avatar
                else:
                    # TODO: Need to use web URL because we can't expose image through static folder.
                    avatar_path = "https://icon-library.com/images/default-profile-icon/default-profile-icon-16.jpg"
                if c.github_author and c.avatar:
                    st.caption(
                        f'<a href="https://github.com/{c.github_author}"><img src="{avatar_path}" style="border: 1px solid #D6D6D9; width: 20px; height: 20px; border-radius: 50%"></a> &nbsp; <a href="https://github.com/{c.github_author}" style="color: inherit; text-decoration: inherit">{c.github_author}</a>',
                        unsafe_allow_html=True,
                    )
                # elif c.github_author:
                #     # TODO: Some of the Github pages extracted above return 404, so
                #     # we can't get the avatar image from them. We could get them by
                #     # querying with the author name directly but for now I'm just hiding the avatar images.
                #     st.caption(
                #         f'<a href="https://github.com/{c.github_author}" style="color: inherit; text-decoration: inherit">{c.github_author}</a>',
                #         unsafe_allow_html=True,
                #     )
                elif c.pypi_author:
                    st.caption(
                        f'<a href="https://pypi.org/user/{c.pypi_author}"><img src="{avatar_path}" style="border: 1px solid #D6D6D9; width: 20px; height: 20px; border-radius: 50%"></a> &nbsp; <a href="https://pypi.org/user/{c.pypi_author}" style="color: inherit; text-decoration: inherit">{c.pypi_author}</a>',
                        unsafe_allow_html=True,
                    )

                if c.github_description:
                    st.write(shorten(c.github_description))
                elif c.pypi_description:
                    st.write(c.pypi_description)
                if c.package:
                    st.code(f"{install_command} {c.package}", None)
                formatted_links = []
                if c.github:
                    # formatted_links.append(mention("Github", c.github, icon="github", write=False))
                    # formatted_links.append(f"[GitHub]({c.github})")
                    formatted_links.append(f"@(GitHub)({c.github})")
                if c.demo:
                    # formatted_links.append(mention("Demo", c.demo, icon="🎈", write=False))
                    # formatted_links.append(f"[Demo]({c.demo})")
                    formatted_links.append(f"@(🎈)(Demo)({c.demo})")
                if c.forum_post:
                    # formatted_links.append(f"[Forum]({c.forum_post})")
                    # formatted_links.append(mention("Forum", c.forum_post, icon="streamlit", write=False))
                    formatted_links.append(f"@(Forum)({c.forum_post})")
                if c.pypi:
                    # formatted_links.append(f"[PyPI]({c.pypi})")
                    # formatted_links.append(mention("PyPI", c.pypi, icon="📦", write=False))
                    formatted_links.append(f"@(📦)(PyPI)({c.pypi})")

                # st.write(" • ".join(formatted_links), unsafe_allow_html=True)
                mdlit(" &nbsp;•&nbsp; ".join(formatted_links))
                # st.caption(", ".join(c.categories))
                st.write("")
                st.write("")
                st.write("")

        # if i < (min(limit, len(components)) // NUM_COLS) - 1:
        # st.write("---")


if "limit" not in st.session_state:
    st.session_state["limit"] = 60


def show_more():
    st.session_state["limit"] += 40


components = get_components()
description.write(description_text.format(len(components)))

# It's more performant to do the sorting first. It's cached, so even though it's running
# on more elements when done first, we almost always have a cache hit since the list of
# components doesn't change.
components = sort_components(components, sorting)

if not search and not category and sorting != "🐣 Newest":
    "## 🚀 Newcomers"
    st.write("")
    new_components = filter_components(
        components, search, category, newer_than=datetime.now() - timedelta(days=60)
    )
    show_components(new_components, limit=4)

    "## 🌟 All-time favorites"

st.write("")
st.write("")

components = filter_components(components, search, category)
show_components(components, st.session_state["limit"])

if len(components) > st.session_state["limit"]:
    st.button("Show more components", on_click=show_more, type="primary")

# if st.button("write additional data file"):
#     yaml_dict = {
#         c.pypi.split("/")[-2]: {"categories": [""]} for c in components if c.pypi
#     }
#     import yaml

#     with open("additional_data.yaml", "w") as f:
#         yaml.dump(yaml_dict, f, sort_keys=False)


# cols = st.columns(5)
# for page in range(1, 1+ math.ceil(len(components) / 100)):
#     print(page)
#     cols[page - 1].button(f"Page {page}", on_click=set_page, args=(page,))

# downloads = pypistats.recent("streamlit-image-select", "month", format="pandas")["last_month"][0]#.iloc[-1]["downloads"]
# st.write(downloads)

# status_code, text = get("https://pypi.org/project/st-searchbar/")
# soup = BeautifulSoup(text, "html.parser")
# summary = soup.find("p", class_="package-description__summary")
# if summary and summary.text and summary.text != "No project description provided":
#     print("found summary description on pypi:", summary.text)
# print(summary)
