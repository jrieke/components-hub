import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import frontmatter
import httpx
import pypistats
import requests
import streamlit as st
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tqdm import tqdm

TRACKER = "https://discuss.streamlit.io/t/streamlit-components-community-tracker/4634"
load_dotenv()
GH_TOKEN = os.getenv("GH_TOKEN")


@dataclass
class Component:
    name: str = None
    package: str = None
    demo: str = None
    forum_post: str = None
    github: str = None
    pypi: str = None
    image_url: str = None
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


# TODO: Need to actually get this functional.
with open("include.yaml") as f:
    include = yaml.load(f, Loader=yaml.FullLoader)

with open("exclude.yaml") as f:
    exclude = yaml.load(f, Loader=yaml.FullLoader)

with open("overwrite.yaml") as f:
    overwrite = yaml.load(f, Loader=yaml.FullLoader)

with open("categories.yaml") as f:
    categories = yaml.load(f, Loader=yaml.FullLoader)


def get(*args, **kwargs):
    res = requests.get(*args, **kwargs)
    return res.status_code, res.text


def get_github_info(url):
    """Use the GitHub API to retrieve a bunch of information about a repo."""
    url = url.replace("https://", "").replace("http://", "")
    user, repo = url.split("/")[1:3]
    response = requests.get(
        f"https://api.github.com/repos/{user}/{repo}",
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Token {GH_TOKEN}",
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


def parse_github_readme(url):
    """get the image url from the github readme"""
    # TODO: Could do this by getting the raw readme file and not the rendered page.
    # But then it's a lot more difficult to find images, since we need to parse markdown.
    status_code, text = get(
        url,
        headers={
            "Authorization": f"Token {GH_TOKEN}",
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
            or "emojipedia" in srcs
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
        and a.text not in exclude
    ]
    return packages


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

    for li in tqdm(lis, desc="🎈 Crawling Streamlit forum (step 1/5)"):

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
    print("⬇️ Downloading PyPI index (step 2/5)")
    packages = get_all_packages()

    # Step 3: Search through PyPI packages
    # TODO: This could be wrapped in memo as well.
    for p in tqdm(packages, desc="📦 Crawling PyPI (step 3/5)"):
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
    for c in tqdm(components_dict.values(), desc="👾 Crawling Github (step 4/5)"):

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
                        "Authorization": f"Token {GH_TOKEN}",
                    },
                )
                if status_code == 200:
                    c.github = f"https://github.com/{c.pypi_author}/{repo}"
                    if repo != c.package:
                        pass
                        # print(
                        #     f"found github url by mutating package name, original: {c.package}, mutated: {repo}"
                        # )
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
            )

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
    for c in tqdm(
        components_dict.values(),
        desc="🖐 Enriching with manually collected data (step 5/5)",
    ):
        if c.package and c.package in overwrite:
            c.categories = overwrite[c.package]["categories"]
            if "title" in overwrite[c.package]:
                c.name = overwrite[c.package]["title"]
            # TODO: Do this for all other properties as well.

        else:
            c.categories = []
    return list(components_dict.values())


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


components = get_components()


print("✍️ Writing to files")
components_dir = Path("gallery_data/components")
components_dir.mkdir(exist_ok=True, parents=True)

categories_dir = Path("gallery_data/componentCategories")
categories_dir.mkdir(exist_ok=True, parents=True)

json_dict = {"components": {}, "componentCategories": {}}

for c in components:
    # TODO: Need to exclude components without packages above as well.
    if c.package:

        author = ""
        socialUrl = ""
        if c.github_author:
            author = c.github_author
            socialUrl = f"https://github.com/{c.github_author}"
        elif c.pypi_author:
            author = c.pypi_author
            socialUrl = f"https://pypi.org/user/{c.pypi_author}"

        description = ""
        if c.github_description:
            description = shorten(c.github_description)
        elif c.pypi_description:
            description = shorten(c.pypi_description)
        # TODO: Should probably remove newlines above already.
        description = description.replace("\n", "")

        # image = "https://raw.githubusercontent.com/jrieke/components-hub/snowvation/default_image.png"
        # if c.image_url:
        #     image = c.image_url

        stars = 0
        if c.stars:
            stars = c.stars

        post = frontmatter.Post(
            "",
            title=c.name,
            author=author,
            description=description,
            pipLink=f"pip install {c.package}",
            category=c.categories,
            image=c.image_url,
            gitHubUrl=c.github,
            socialUrl=socialUrl,
            componentOfTheWeek=False,
            hostedWithStreamlit=False,
            enabled=True,
            appUrl=c.demo,
            forum=c.forum_post,
            pypi=c.pypi,
            avatar=c.avatar,
            stars=stars,
        )

        frontmatter.dump(post, components_dir / f"{c.package}.md")
        json_dict["components"][c.package] = post.metadata

for i, (category, data) in enumerate(categories.items()):
    # st.write(category, data)
    post = frontmatter.Post(
        "",
        id=category,
        title=data["icon"] + " " + data["title"],
        enabled=True,
        icon=data["icon"],
        order=i,
    )
    frontmatter.dump(post, categories_dir / f"{category}.md")
    json_dict["componentCategories"][category] = post.metadata

    # Write json_dict to a json file
    with open("gallery_data/components.json", "w") as f:
        json.dump(json_dict, f, indent=4)

    with open("gallery_data/components.yaml", "w") as f:
        yaml.dump(json_dict, f)
