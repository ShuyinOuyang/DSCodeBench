import json
import os
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import time
import scrapy
import re

def make_soup(url):
    response = requests.get(url)
    time.sleep(1)
    if response.status_code == 200:
        return BeautifulSoup(response.text, 'html.parser')
    else:
        print(response)
    return None

def get_detail_of_question_from_search_page(base_url, question):
    # question: soup object
    detail = {}
    # stats
    stats = question.find('div', class_='s-post-summary--stats')
    # votes_num, answers_num, and views_num are string
    votes = stats.find('div', class_='s-post-summary--stats-item__emphasized').text.replace('votes', '').strip()
    answers = stats.find('div', class_='has-answers').text.replace('answers', '').strip()
    if stats.find('div', class_='is-supernova'):
        views = stats.find('div', class_='is-supernova').text.replace('views', '').strip()
    else:
        views = stats.find('div', class_='is-hot').text.replace('views', '').strip()
    # content
    content = question.find('div', class_='s-post-summary--content')
    title = content.find(class_='s-post-summary--content-title').text.strip()
    link = content.find(class_='s-post-summary--content-title').a['href']
    question_link = base_url + link
    detail['votes'] = votes
    detail['answers'] = answers
    detail['views'] = views
    detail['title'] = title
    detail['question_link'] = question_link
    return detail

def get_post_comment(tag):
    comments = []
    for c in tag.select('.comment-copy'):
        comments.append(c.get_text())
    return comments

def get_detail_of_question_from_question_page(question_soup, detail):
    question_related = question_soup.select('#question')[0]
    question_content = question_related.select('.s-prose,.js-post-body')[0].text.strip()
    question_comment = get_post_comment(question_related)
    answer_related = question_soup.select('#answers')[0]
    answers = []
    a_count = 0
    for a in answer_related.contents:
        if type(a).__name__ == 'Tag':
            if a.name == 'div' and (a.get('class') is not None and 'answer' in a.get('class')):
                answer_content = a.select('.s-prose,.js-post-body')[0].text.strip()
                answer_comment = get_post_comment(a)
                answer_score = a['data-score']
                answer_class = a['class']
                if 'accepted-answer' in answer_class:
                    is_accepted = True
                else:
                    is_accepted = False
                answer_code_list = []
                code_search_res = a.find_all('pre')
                for code_tag in code_search_res:
                    answer_code_list.append(code_tag.text)
                answers.append({
                    'answer_content': answer_content,
                    'answer_comment': answer_comment,
                    'answer_score': answer_score,
                    'answer_code_list': answer_code_list,
                    'is_accepted': is_accepted
                })
                a_count += 1
    detail['question_content'] = question_content
    detail['question_comment'] = question_comment
    detail['answers'] = answers
    return detail


# extract data from stackoverflow
# Seaborn
# LightGBM
# Keras
def extract_data_from_stackoverflow(keyword='seaborn', save=False):
    detail_list = []
    base_url = 'https://stackoverflow.com'
    _url = 'https://stackoverflow.com/questions/tagged/{keyword}?page={page}&sort=votes&pagesize=50'
    urls = [_url.format(keyword=keyword, page=page) for page in range(1, 10)]

    for url in urls:
        print(url)
        soup = make_soup(url)
        try:
            questions = soup.find(id='questions')
        except:
            continue
        for child in questions.find_all('div', recursive=False):
            try:
                detail = get_detail_of_question_from_search_page(base_url, child)
                question_soup = make_soup(detail['question_link'])
                detail = get_detail_of_question_from_question_page(question_soup, detail)
                detail_list.append(detail)
            except:
                continue

    # store the result
    if save:
        if not os.path.exists('stackoverflow_new_data/'):
            os.makedirs('stackoverflow_new_data/')
        with open('stackoverflow_new_data/%s.json' % keyword, 'w') as f:
            f.write(json.dumps(detail_list))


if __name__ == '__main__':
    library_list = ['seaborn', 'keras', 'lightgbm']
    save = False
    for library in library_list:
        extract_data_from_stackoverflow(library, save)