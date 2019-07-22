import requests
from bs4 import BeautifulSoup
# from lxml import html
from decimal import *
import pandas as pd
import re
from smtplib import SMTP

shipping_options = {
    'prime': '&f_primeEligible=true',
    'free_shipping': '&f_freeShipping=true',
    'prime_or_free': '&f_freeShipping=true&f_primeEligible=true',
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

def build_url(asin, condition='all', shipping='all'):
    url = 'https://amazon.com/gp/offer-listing/' + asin + '/ref=' + condition_options[condition] + shipping_options[shipping]
    return url

def notify(row, url, sender, recipient, password):
    # print(row.head())
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

    print('Email sent to {}'.format(recipient))

    server.quit()

def scrape(url):
    response = requests.get(url, headers=headers)
    if response.status_code == 403:
        print("bad")
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

        print(short_ft.head(10))
        # print(listings[0])

        if df['Total'][0] < 160:
            notify(df.head(1), url, 'noahzanetigner@gmail.com', 'noahzanetigner@gmail.com', 'temp')


if __name__ == '__main__':
    asin = 'B075HRTD2C' # Amazon Standard Identification Number (ASIN)
    url = build_url(asin, condition='all', shipping='all')
    scrape(url)

