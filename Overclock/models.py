import http

from django.db import models

# Create your models here.
class User(models.Model):
    name = models.CharField(max_length=100)
    email=models.EmailField()
    password = models.CharField(max_length=128)
    address = models.CharField(max_length=200)
    phone=models.IntegerField()
    def __str__(self):
        return f"{self.name}"

# Product model to store product information

class Product(models.Model):
    name = models.CharField(max_length=150)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField()
    category = models.CharField(max_length=100)
    image = models.ImageField(upload_to='products/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    
class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_price(self):
        return self.product.price * self.quantity
    
class Feedback(models.Model):
    RATING_CHOICES=[
        (1,'1'),
        (2,'2'),
        (3,'3'),
        (4,'4'),
        (5,'5'),
    ]
    feedback_text=models.TextField()
    rating=models.IntegerField(choices=RATING_CHOICES)
    created_at=models.DateTimeField(auto_now_add=True)
    email=models.EmailField()
    def __str__(self):
        return f"Feedback from {self.email}"
    

class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
 
    def __str__(self):
        return f"{self.name} ({self.email})"
    
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_digital = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

import uuid

class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending',    'Pending'),
        ('Processing', 'Processing'),
        ('Shipped',    'Shipped'),
        ('Delivered',  'Delivered'),
    ]
    PAYMENT_CHOICES = [
        ('COD',  'Cash on Delivery'),
        ('UPI',  'UPI'),
        ('CARD', 'Credit/Debit Card'),
    ]

    order_id       = models.CharField(max_length=20, unique=True, editable=False)
    # user is optional — supports guest checkout
    user           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    # contact info (filled by guest or pre-filled for logged-in users)
    full_name      = models.CharField(max_length=100)
    email          = models.EmailField()
    phone          = models.CharField(max_length=15)
    address        = models.TextField()
    city           = models.CharField(max_length=100)
    pincode        = models.CharField(max_length=10)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES)
    # UPI / Card details (stored as plain text for academic purposes)
    upi_id         = models.CharField(max_length=100, blank=True, null=True)
    card_number    = models.CharField(max_length=20,  blank=True, null=True)
    card_expiry    = models.CharField(max_length=7,   blank=True, null=True)
    card_cvv       = models.CharField(max_length=4,   blank=True, null=True)

    delivery_email  = models.EmailField(blank=True, null=True)   # email for digital delivery
    license_key     = models.TextField(blank=True, null=True)    # filled by admin for digital products

    subtotal       = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee   = models.DecimalField(max_digits=10, decimal_places=2)
    grand_total       = models.DecimalField(max_digits=10, decimal_places=2)
    promo_code        = models.CharField(max_length=50, blank=True, null=True)
    discount_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at     = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.order_id:
            self.order_id = 'OC' + uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_id} — {self.full_name}"

    class Meta:
        ordering = ['-created_at']


class OrderItem(models.Model):
    order         = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_name  = models.CharField(max_length=150)
    product_image = models.CharField(max_length=300, blank=True)
    price         = models.DecimalField(max_digits=10, decimal_places=2)
    quantity      = models.IntegerField()
    is_digital    = models.BooleanField(default=False)

    @property
    def total(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"
    
class Promotion(models.Model):
    PROMO_TYPE_CHOICES = [
        ('PERCENTAGE',   'Percentage Off'),
        ('FREE_PRODUCT', 'Free Product with Purchase'),
    ]

    name                = models.CharField(max_length=150)
    description         = models.TextField(help_text="Shown on banners e.g. '20% off all GPUs'")
    promo_type          = models.CharField(max_length=20, choices=PROMO_TYPE_CHOICES)

    # PERCENTAGE fields
    discount_percent    = models.IntegerField(null=True, blank=True)         # e.g. 20
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2,
                                              null=True, blank=True)         # e.g. 20000 (cap), blank = no cap

    # FREE_PRODUCT fields
    free_product        = models.ForeignKey('Product', null=True, blank=True,
                                            on_delete=models.SET_NULL,
                                            related_name='free_in_promos')

    # Targeting
    applies_to_category = models.CharField(max_length=100, blank=True,
                                           help_text="Leave blank to apply to entire cart")
    coupon_code         = models.CharField(max_length=50, unique=True,
                                           help_text="User enters this at checkout")

    # Validity — manual admin control
    start_date          = models.DateTimeField()
    end_date            = models.DateTimeField()
    is_active           = models.BooleanField(default=False)

    created_at          = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} [{self.coupon_code}]"

    @property
    def is_valid_now(self):
        from django.utils import timezone
        from django.utils.timezone import make_aware, is_naive
        now = timezone.now()
        start = make_aware(self.start_date.replace(tzinfo=None)) if is_naive(self.start_date) else self.start_date
        end   = make_aware(self.end_date.replace(tzinfo=None))   if is_naive(self.end_date)   else self.end_date
        return self.is_active and start <= now <= end

    class Meta:
        ordering = ['-created_at']