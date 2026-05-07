from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Product

class StaticViewSitemap(Sitemap):
    priority    = 0.8
    changefreq  = 'weekly'

    def items(self):
        return ['index', 'all_products', 'about', 'contact', 'feedback']

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    changefreq  = 'daily'
    priority    = 0.9

    def items(self):
        return Product.objects.all()

    def location(self, obj):
        # links to all_products filtered by this product's category
        return f'/all-products/?category={obj.category}'