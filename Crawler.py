import requests
import schedule
import time
import arrow
from lxml import html
from lxml.cssselect import CSSSelector
from tinydb import TinyDB, where
import atexit

# proxies for connect to tor network.
proxies = {
    'http': 'http://10.0.2.15:8118',
    'https': 'https://10.0.2.15:8118'
}


class PasteModel:
    """Paste model class will store all the attributes of pastes."""
    def __init__(self, author="", title="", content="", date=None):
        self.author = author
        self.title = title
        self.content = content
        self.date = date


class Crawler:
    """Crawler class that will be responsible for crawling."""
    def __init__(self, url, database):
        self.url = url
        self.database = database

    def start_crawling(self):
        """Main function of crawler. Every 4 hours this function will be called.
        Will start crawl the url saved as member.
        :return: None.
        """
        try:
            print("Start crawling.")
            page = requests.get(self.url, proxies=proxies)
            parser = HtmlScraper(page, self.database)
            # start parsing function will return number of new pastes that stored in db.
            new_pastes = parser.start_parsing()
            print("Finish crawling. Amount of new pastes are: " + str(new_pastes))
        except requests.RequestException:
            print("OnStart")
            print("Request exception occurred. Url: " + self.url)


class HtmlScraper:
    """"""
    """"Html parser class. This class is responsible for scrapping the site and get all the new pastes,
    that not added yet to the db.
    """
    def __init__(self, page, database):
        self.month_dict = dict(jan='01', feb='02', mar='03', apr='04', may='05', jun='06', jul='07', aug='08', sep='09',
                               oct='10', nov='11', dec='12')
        self.page = page
        self.database = database
        self.new_pastes = 0    # number of new pastes added for all session.
        self.page_pastes = 0    # number of new pastes added per site.
        self.stop_parsing = False

    def get_date(self, data):
        """This function returns date in UTC format, by parsing the content from not valid words. Every month
        converted to his number representation via month dict.
        :param data: data to parsed to Date.
        :return: Date in UTC format.
        """
        data = data.lower().replace('posted by', '').replace('at', '').replace('utc', '').replace('anonymous', '') \
            .replace(',', '').strip()
        for month in self.month_dict:
            if month in data:
                data = data.replace(' ' + month + ' ', '-' + self.month_dict[month] + '-')
                break
        return arrow.get(data, 'DD-MM-YYYY HH:mm:ss')

    def start_parsing(self):
        """
        Parsing function responsible to scrap site by site till there is no new pastes to be added to db.
        For each web page collect all the pastes data of this page and insert all the list of pasted to db.
        The loop inside the function will runs till the boolean stop parsing will turned on. And it will happen
        if we reached old pastes.
        :return: Number of new pastes added to db.
        """
        tree = html.fromstring(self.page.content)
        while not self.stop_parsing:
            pastes_date = self.parse_date(tree)
            pastes_author = self.parse_author(tree)
            pastes_title = self.parse_title(tree)
            pastes_content = self.parse_content(tree)
            pastes_model_list = self.create_pastes(pastes_title, pastes_author, pastes_date, pastes_content)
            self.database.update_data_base(pastes_model_list)
            self.update_next_page(tree)
            tree = html.fromstring(self.page.content)
            self.new_pastes += self.page_pastes
            self.page_pastes = 0
        return self.new_pastes

    def update_next_page(self, tree):
        """
        Function checks in the page content what is the next page to be scrapped,
        if there is new page get request for this page and update class member to be new page.
        :param tree:
        :return: None
        """
        link_selector = CSSSelector('a')
        pages_selector = CSSSelector('ul.pagination li')
        all_pages_lists = pages_selector(tree)
        try:
            # make select on the last page in pages list take his url from 'href' attr.
            url = link_selector(all_pages_lists[-1])[0].get('href')
            self.page = requests.get(url, proxies=proxies)
        except IndexError:
            self.stop_parsing = True

    def parse_author(self, tree):
        """
        Get list of all authors of new pastes.
        :param tree: The tree content of the page.
        :return: List of authors.
        """
        data_content = tree.xpath("//div[@class='col-sm-6']")
        user_link_selector = CSSSelector('a')
        pastes_author = []
        i = 0
        for data in data_content:
            # if number of pastes for now equal to the amount of new pastes, break.
            if i == self.page_pastes:
                break
            user = user_link_selector(data)
            name = ""
            # if 'div' element have 'a' as son element, meaning this paste have user specified.
            if len(user) != 0:
                name = user[0].text
            pastes_author.append(name)
            i += 1
        return pastes_author

    def parse_title(self, tree):
        """
        Get list of title of new pastes.
        :param tree: The tree content of the page.
        :return: List of titles.
        """
        title_selector = CSSSelector('div.col-sm-5 h4')
        pastes_title = []
        pastes_title_list = title_selector(tree)
        i = 0
        for paste_title in pastes_title_list:
            if i == self.page_pastes:
                break
            pastes_title.append(paste_title.text.strip())
            i += 1
        return pastes_title

    def parse_content(self, tree):
        """
        Get list of all contents of new pastes.
        :param tree: The tree content of the page.
        :return: List of contents.
        """
        # selector for all pastes 'url' to their content.
        content_link_selector = CSSSelector('div.col-sm-7 a')
        pastes_content = []
        pastes_links = content_link_selector(tree)
        i = 0
        # iterate over every link
        for link in pastes_links:
            if i == self.page_pastes:
                break
            url = link.get('href')
            page = requests.get(url, proxies=proxies)    # request for this page via url and get the page.
            tree = html.fromstring(page.content)
            lines = tree.xpath("//div[starts-with(@style,'font')]/text()")    # get list of all lines in tree.
            content = ""
            for line in lines:
                if len(line.strip()) != 0:    # skip empty lines.
                    content = content + line + '\n'
            pastes_content.append(content)
            i += 1
        return pastes_content

    def parse_date(self, tree):
        """
        Get list of all dates of new pastes. This function responsible for checking for every paste's date if
        he is already in db, and update the member 'page_pastes' by 1 if this paste is not in db meaning this
        paste is new.
        :param tree: The tree content of the page.
        :return: List of dates.
        """
        date_content = tree.xpath("//div[@class='col-sm-6']/text()[last()]")
        pastes_date = []
        for temp_date in date_content:
            date = self.get_date(temp_date)
            if self.database.query_date(str(date)):  # query the db for this paste's date. Only dates are unique in db
                break
            pastes_date.append(date)
            self.page_pastes += 1
        if self.page_pastes != len(date_content):    # if the number of new pastes not equal to the amount of all
            self.stop_parsing = True                 # page's pastes meaning we broke from the loop. Meaning we reached
        return pastes_date                           # old paste.

    @staticmethod
    def create_pastes(pastes_title, pastes_name, pastes_date, pastes_content):
        """
        Static function that combines all the list's to one main list of PasteModal type.
        :param pastes_title: List of titles.
        :param pastes_name: List of authors.
        :param pastes_date: List of dates.
        :param pastes_content: List of contents.
        :return: Return list of all pastes combined in one.
        """
        pastes = []
        for i in range(0, len(pastes_title)):
            paste = PasteModel(pastes_name[i], pastes_title[i], pastes_content[i], pastes_date[i])
            pastes.append(paste)
        return pastes


class DataBase:
    """
    Data base class responsible for queries and updating of new pastes.
    """
    def __init__(self, db):
        self.db = db

    def update_data_base(self, new_pastes):
        """
        Update db by iterate over all lists and insert every paste one by one.
        :param new_pastes: List of all pastes.
        :return: None
        """
        for paste in new_pastes:
            self.db.insert({'author': paste.author, 'title': paste.title,
                            'content': paste.content, 'date': str(paste.date)})

    def query_date(self, value):
        """
        Query the db if specified date is contained im db.
        :param value: Value to be checked.
        :return: Return true if yes, no otherwise
        """
        return self.db.contains(where('date') == value)

    def clear_db(self):
        """
        Clear all db.
        :return: None
        """
        self.db.purge()

    def get_number_of_documents(self):
        """
        Get the number of elements in db.
        :return: The number of elements.
        """
        return len(self.db)


def job():
    """
    Scheduler function that will be called every 4 hours and will create crawler and start crawling.
    :return: None
    """
    crawler = Crawler('http://nzxj65x32vh2fkhk.onion/all', DataBase(TinyDB('db.json')))
    crawler.start_crawling()


def main():
    # first time iterate over whole site.
    job()
    schedule.every(1).minutes.do(job)
    # loop forever till the service will be stopped.
    while status_service:
        schedule.run_pending()
        time.sleep(1)


status_service = True


def close_crawler_service():
    print("Closing service")


atexit.register(close_crawler_service)

if __name__ == '__main__':
    main()
