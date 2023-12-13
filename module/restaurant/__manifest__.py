{
    "name": "Restaurant 1.0.0",
    "version": "1.0.0",
    "author": "Chau Quang Minh",
    "category": "Restaurant",
    "website": "",
    "depends": ['account', 'sale', 'sale_stock', 'product', 'sale_discount_total'],
    "license": "AGPL-3",
    "summary": "Restaurant Management to manage Restaurant Configuration",
    "data": [
        "security/ir.model.access.csv",
        "views/configuration.xml",
        "views/dashboard.xml",
        "views/table.xml",
        "views/restaurant.xml",
        "views/tablevirtual.xml",
    ],
    "qweb": [
    ],
    "images": ["static/description/restaurant.png"],
    "application": True,
}