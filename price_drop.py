import requests
from bs4 import BeautifulSoup
# from lxml import html
from decimal import *
import pandas as pd
import re
from smtplib import SMTP
import argparse
import os.path
from os import path
import sqlite3
from sqlite3 import Error
import time
from datetime import datetime, timedelta

def build_url(asin, condition='all', shipping='all'):
    url = 'https://amazon.com/gp/offer-listing/' + asin + '/ref=' + condition_options[condition] + shipping_options[shipping]
    return url

def notify(row, url, sender, recipient, password):
    
    server = SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.ehlo()

    server.login(sender, password)

    subject = 'The price of an item you\'re following fell!'
    data = row.iloc[0, :].to_dict()
    body = """Item: {}\nTotal: {}\nCondition: {}\nSeller: {}\nURL: {}\n\nBe sure to select the option shown above ;)
           """.format(data['Item'], data['Total'], data['Condition'], data['Seller'] + ', ' + data['Location'], url)
    message = f'Subject: {subject}\n\n{body}'

    server.sendmail(
        sender,
        recipient,
        message
    )

    print('\nEmail sent to {}\n'.format(recipient))

    server.quit()

def db_create_connection(db_file):

    try:
        connection = sqlite3.connect(db_file)
        return connection
    except Error as e:
        print(repr(e))
        return None

def db_create_table(connection):
    try:
        statement = """ CREATE TABLE IF NOT EXISTS prices (
                            datetime DATETIME NOT NULL,
                            item TEXT NOT NULL,
                            total DECIMAL(30, 2) NOT NULL,
                            seller TEXT NOT NULL
                        );
                    """
        cursor = connection.cursor()
        cursor.execute(statement)
    except Error as e:
        print(e)

def db_insert_entry(connection, entry):
    try:
        statement = """ INSERT INTO prices (datetime, item, total, seller)
                        VALUES(?, ?, ?, ?)
                    """
        cursor = connection.cursor()
        cursor.execute(statement, entry)
        return cursor.lastrowid
    except Error as e:
        print(e)

def db_select_item(connection, item):
    try:
        statement = """ SELECT * FROM prices
                        WHERE item = ?
                    """
        cursor = connection.cursor()
        cursor.execute(statement, (item,))

        rows = cursor.fetchall()
        for row in rows:
            print(row)
    except Error as e:
        print(e)


def scrape(url, email, password):
    response = requests.get(url, headers=headers)
    if response.status_code == 403:
        print("403")
    else:
        rows = []

        soup = BeautifulSoup(response.text, 'lxml')
        listings = soup.find_all("div", 'a-row a-spacing-mini olpOffer', limit=99)

        for listing in listings:

            price = listing.find('span', 'a-color-price').string.strip()
            price = Decimal(price.replace('$', ''))

            ship_price = 0
            if listing.find('span', 'olpShippingPrice'):
                ship_price = listing.find('span', 'olpShippingPrice').string.strip()
                ship_price = Decimal(ship_price.replace('$', ''))

            total = price + ship_price

            condition = listing.find('span', 'olpCondition').string.strip()

            delivery = listing.find('div', 'olpDeliveryColumn').find('span', 'a-list-item').string.strip() \
                                                                                        .replace('.', '') \
                                                                                        .replace('United States', 'US') \
                                                                                        .replace('Ships from ', '')

            # seller = listing.find('div', 'olpSellerName').find('a').string.strip()

            seller = listing.find('h3', 'olpSellerName').find('a').text.strip()
            seller = re.sub('[^0-9a-zA-Z ]+', '*', seller)

            rating = listing.find('div', 'olpSellerColumn').find('b').string.strip().replace(' positive', '')

            row = {
                'Item': asin, 
                'Total': total,
                'Price': price, 
                'Shipping': ship_price, 
                'Condition': condition, 
                'Seller': seller,
                'Location': delivery,
                'Seller Rating': rating
            }
            rows.append(row)


            # print('Total: {}, Price: {}, Shipping: {}, Condition: {}, Delivery: {}'.format(price+ship_price, price, ship_price, condition, delivery))
            # price = float(price.replace('$', ''))
            # print(price)

        df = pd.DataFrame(rows, columns=['Item', 'Total', 'Price', 'Shipping', 'Condition', 'Seller', 'Location', 'Seller Rating'])
        df = df.sort_values(by=['Item', 'Total'], ascending=[1, 1])
        short_ft = df[['Item', 'Total', 'Condition', 'Seller', 'Location', 'Seller Rating']]

        print('\nBest Current Listings:\n')
        print(short_ft.head(3))
        # print(listings[0])

        # if df['Total'][0] < 160:
        #     notify(df.head(1), url, email, email, password)   # 'rcesuiarnwengbff'

        return df.head(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('asin', help='Amazon Standard Identification Number, eg "B075HRTD2C"', default='B075HRTD2C')
    parser.add_argument('condition', help='Options: new, used, usedAcceptable, usedGood, usedVeryGood, usedLikeNew, all', default='all')
    parser.add_argument('shipping', help='Options: prime, freeShipping, primeOrFree, all', default='all')
    parser.add_argument('email', help='Your email address')
    parser.add_argument('password', help='Your email password. See https://myaccount.google.com/apppasswords')
    
    args = parser.parse_args()
    asin = args.asin
    condition = args.condition
    shipping = args.shipping
    email = args.email
    password = args.password

    shipping_options = {
        'prime': '&f_primeEligible=true',
        'freeShipping': '&f_freeShipping=true',
        'primeOrFree': '&f_freeShipping=true&f_primeEligible=true',
        'all': '&shipping=all'
    }

    condition_options = {
        'new': '&f_new=true',
        'used': '&f_usedAcceptable=true&f_usedGood=true&f_usedVeryGood=true&f_usedLikeNew=true',
        'usedAcceptable': '&f_usedAcceptable=true',
        'usedGood': '&f_usedGood=true',
        'usedVeryGood': '&f_usedVeryGood=true',
        'usedLikeNew': '&f_usedLikeNew=true',
        'all': '&f_condition=all'
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5) AppleWebKit/537.36 (KHTML, like Gecko) \
                    Chrome/75.0.3770.100 Safari/537.36'
    }

    

    url = build_url(asin, condition=condition, shipping=shipping)
    # scrape(url, email, password)
    start_time = time.time()
    while True:
        row = scrape(url, email, password)
        data = row.iloc[0, :].to_dict()
        # print(data)

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')   # 9999-12-31 23:59:59
        print(now)

        # db_insert_entry(connection, ('2019-07-22', 'test', 100, 'test'))




        time.sleep(60.0 - ((time.time() - start_time) % 60.0))


    # connection = db_create_connection('records.db')
    # db_create_table(connection)
    # db_insert_entry(connection, ('2019-07-22', 'test', 100, 'test'))
    # db_insert_entry(connection, ('2019-07-12', 'test', 200, 'test'))
    # db_select_item(connection, 'test')
    # connection.close()

