import requests
from bs4 import BeautifulSoup
# from lxml import html
from decimal import *
import pandas as pd
import re
from smtplib import SMTP
import argparse
from argparse_prompt import PromptParser
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

def adapt_decimal(d):
    return str(d)

def convert_decimal(s):
    return Decimal(s)

def db_create_connection(db_file):

    try:
        connection = sqlite3.connect(db_file)
        return connection
    except Error as e:
        print('Error: ' + str(e))
        return None

def db_create_table(connection):
    try:
        statement = """ CREATE TABLE IF NOT EXISTS prices (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            datetime DATETIME NOT NULL,
                            item TEXT NOT NULL,
                            total DECIMAL(30, 2) NOT NULL,
                            seller TEXT NOT NULL
                        );
                    """
        cursor = connection.cursor()
        cursor.execute(statement)
        connection.commit()
    except Error as e:
        print('Error: ' + str(e))

def db_insert_entry(connection, entry):
    try:
        statement = """ INSERT INTO prices (datetime, item, total, seller)
                        VALUES(?, ?, ?, ?);
                    """
        cursor = connection.cursor()
        cursor.execute(statement, entry)
        connection.commit()
        return cursor.lastrowid
    except Error as e:
        print('Error: ' + str(e))

def db_select_item(connection, item):
    try:
        last_week = (datetime.now() - timedelta(7)).strftime('%Y-%m-%d %H:%M:%S')
        today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        statement = """ SELECT AVG(total),  MIN(total)
                        FROM prices
                        WHERE item=?
                        AND  datetime >= ? and datetime <= ?
                    """
        cursor = connection.cursor()
        cursor.execute(statement, (item, last_week, today))
        rows = cursor.fetchall()

        return (round(Decimal(rows[0][0]), 2), rows[0][1])

    except Error as e:
        print('Error: ' + str(e))

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

        df = pd.DataFrame(rows, columns=['Item', 'Total', 'Price', 'Shipping', 'Condition', 'Seller', 'Location', 'Seller Rating'])
        df = df.sort_values(by=['Item', 'Total'], ascending=[1, 1])

        return df.head(3)


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

    # TODO: if arg is missing, prompt for it
    # parser = PromptParser()
    # parser.add_argument('asin', help='Amazon Standard Identification Number', default='B075HRTD2C')

    # args = parser.parse_args()
    # asin = args.asin

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

    start_time = time.time()
    
    connection = db_create_connection('records.db')
    db_create_table(connection)
    sqlite3.register_adapter(Decimal, adapt_decimal)        # Register the adapter
    sqlite3.register_converter("decimal", convert_decimal)  # Register the converter

    percentage_lower = Decimal(.05)
    interval = 60   # 60 minutes

    while True:
        rows = scrape(url, email, password)

        print('\nBest Current Listings:\n')
        print(rows.head(3))

        data = rows.iloc[0, :].to_dict()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')   # 9999-12-31 23:59:59
  
        entry = (now, data['Item'], data['Total'], data['Seller'])
        db_insert_entry(connection, entry)

        (historical_average, historical_minimum) = db_select_item(connection, data['Item'])
        print('\nAverage Low Price: {}, Lowest Historical Price: {}, Current Lowest Price: {}\n'.format(str(historical_average), str(historical_minimum), data['Total']))

        # FIXME: better scheduling
        # dt = datetime.now() # + timedelta(hours=0)
        # dt = dt.replace(minute=48)
        # if datetime.now() == dt:
        #     print("match")

        if (data['Total'] < (Decimal(historical_minimum / 100) - percentage_lower) * 100) or (data['Total'] < (Decimal(historical_average / 100) - percentage_lower) * 100):
            notify(rows.head(1), url, email, email, password)

        print('-'*64)

        time.sleep(interval * 60.0 - ((time.time() - start_time) % 60.0)) 

    connection.close()
