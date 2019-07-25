import requests
from bs4 import BeautifulSoup
from decimal import *
import pandas as pd
import re
from smtplib import SMTP
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import argparse
import sqlite3
from sqlite3 import Error
import time
from datetime import datetime, timedelta
from utils.utilities import my_print as print
from utils.utilities import my_input as input
from utils.utilities import ProgressBar, CountDown
import sys

def build_url(asin, condition='all', shipping='all'):
    url = 'https://amazon.com/gp/offer-listing/' + asin + '/ref=' + condition_options[condition] + shipping_options[shipping]
    return url

def notify(row, url, sender, recipient, password, width=64):

    p2 = ProgressBar(name='Deal Found!', steps=5, width=width, completion='Email Sent to {}'.format(recipient))

    smtp_server = 'smtp.gmail.com'
    port = 587

    p2.update(step_name='Creating Secure SSL Connection')
    context = ssl.create_default_context()

    p2.update(step_name='Preparing Message')
    data = row.iloc[0, :].to_dict()

    message = MIMEMultipart('alternative')
    message['Subject'] = f'The price of an item you\'re following fell!'
    message["From"] = sender
    message['To'] = recipient

    plain_text = (
        f"Item: {data['Item']}" 
        f"Total: {data['Total']}"
        f"Condition: {data['Condition']}" 
        f"Seller: {data['Seller']}, {data['Location']}" 
        f"URL: {url}" 
        f"\nBe sure to select the seller show above :)"
    )

    html_text = (
        f"<html><body><p>"
        f"<strong>Item: </strong>{data['Item']}"
        f"<br><strong>Total: </strong>{data['Total']}"
        f"<br><strong>Condition: </strong>{data['Condition']}" 
        f"<br><strong>Seller: </strong>{data['Seller']}, {data['Location']}" 
        f"<br><strong>URL: </strong>{url}" 
        f"<br><br>Be sure to select the seller show above :)"
        f"</p></body></html>"
    )

    message.attach(MIMEText(plain_text, 'plain'))
    message.attach(MIMEText(html_text, 'html'))

    try:
        p2.update(step_name='Connecting to Email Server')
        server = SMTP(smtp_server, port)
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()

        p2.update(step_name='Logging in to Server')
        server.login(sender, password)

        p2.update(step_name='Sending Notification')
        server.sendmail(
            sender,
            recipient,
            message.as_string()
        )
    except Exception as e:
        print(e, color='red')
    finally:
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
        print('Error: ' + str(e), color='red')
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
        print('Error: ' + str(e), color='red')

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
        print('Error: ' + str(e), color='red')

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
        print('Error: ' + str(e), color='red')

def scrape(url, p=None):

    p.update(step_name='Requesting Data from Amazon.com')
    response = requests.get(url, headers=headers)

    if response.status_code == 403:
        print("403", color='red')
    else:
        rows = []

        p.update(step_name='Gathering Data')
        soup = BeautifulSoup(response.text, 'lxml')
        listings = soup.find_all("div", 'a-row a-spacing-mini olpOffer', limit=99)

        p.update(step_name='Scraping Listings')
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

    parser = argparse.ArgumentParser()
    parser.add_argument('asin', help='Amazon Standard Identification Number, eg "B075HRTD2C"')
    parser.add_argument('condition', help='Options: new, used, usedAcceptable, usedGood, usedVeryGood, usedLikeNew, all')
    parser.add_argument('shipping', help='Options: prime, freeShipping, primeOrFree, all')
    parser.add_argument('email', help='Your email address')
    parser.add_argument('password', help='Your email password. See https://myaccount.google.com/apppasswords')
    parser.add_argument('interval', help='How many minutes there are between iterations')

    # TODO: better decision making
    # TODO: handle and track multiple items
    
    # TODO: hide this error, then split these up and make util
    try:
        args = parser.parse_args()
        asin = args.asin
        condition = args.condition
        shipping = args.shipping
        recipient = args.email
        interval = float(args.interval)
    except SystemExit as e:
        print()
        asin = input('Enter Item\'s ASIN: ', default='B075HRTD2C', color='yellow')
        condition = input('Enter Condition: ', options=condition_options.keys(), default='all', color='yellow') 
        shipping = input('Enter Shipping Constraint: ', options=shipping_options.keys(), default='all', color='yellow') 
        recipient = input('Enter Your Email: ', default='noahzanetigner@gmail.com', color='yellow') 
        interval = float(input('Enter Interval in Minutes: ', default=60, color='yellow'))
        
    sender = 'pricedroppy@gmail.com'
    password = 'aobwarerhxszoswb'

    url = build_url(asin, condition=condition, shipping=shipping)

    percentage_lower = Decimal(.05)
    recent = 9999999999
    width = 40

    while True:

        start_time = time.time()

        # Begin Scraping
        # ----------------------------------------------------------------
    
        p1 = ProgressBar('Scraping Data', steps=8, width=width, completion='Data Gathered, Stored, and Compared')

        p1.update(step_name='Connecting to Database')
        connection = db_create_connection('records.db')

        p1.update(step_name='Accessing Database Tables')
        db_create_table(connection)

        p1.update(step_name='Registering Adapters')
        sqlite3.register_adapter(Decimal, adapt_decimal)
        sqlite3.register_converter("decimal", convert_decimal)

        rows = scrape(url, p1)

        # Parse Data, Upload to DB, Query DB
        # ----------------------------------------------------------------

        data = rows.iloc[0, :].to_dict()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')   # 9999-12-31 23:59:59
  
        p1.update(step_name='Inserting New Data into Database')
        entry = (now, data['Item'], data['Total'], data['Seller'])
        db_insert_entry(connection, entry)

        p1.update(step_name='Comparing to Database Records')
        (historical_average, historical_minimum) = db_select_item(connection, data['Item'])

        # Print Data
        # ----------------------------------------------------------------

        print('\nData Gathered {}'.format(datetime.now().strftime('%m-%d-%Y %H:%M')))
        print('Best Current Listings:\n')
        print(rows.head(3))

        print('\nAverage Price on Record: {}, Lowest Price on Record: {}, Current Lowest Price: {}\n'.format(str(historical_average), str(historical_minimum), data['Total']))
          
        # Decisions about what makes a price a good deal are made here
        # ----------------------------------------------------------------

        if (data['Total'] < (Decimal(historical_minimum / 100) - percentage_lower) * 100) \
            or ((data['Total'] < (Decimal(historical_average / 100) - percentage_lower) * 100) \
            and data['Total'] < recent):

            notify(rows.head(1), url, sender=sender, recipient=recipient, password=password, width=width)


        # Clean Things Up, Repeat After Interval
        # ----------------------------------------------------------------

        connection.close()
        recent = data['Total']

        CountDown(minutes=interval, message='Restarting in:', completion=(' '*32) + '\n')#, completion= (' '*32) + '\n|' + ('='*64) + '|\n\n|'+ ('='*64) + '|\n')
    