import email
from django.views.decorators.cache import never_cache
from django.shortcuts import render, redirect, get_object_or_404
from .models import *
from django.contrib import messages
from django.http import HttpResponse, JsonResponse 
from django.contrib.auth.hashers import make_password, check_password

def index(request):
    active_promos = [p for p in Promotion.objects.filter(is_active=True) if p.is_valid_now]
    return render(request, 'index.html', {'active_promos': active_promos})

def admin_required(view_func):
    """Decorator to protect admin-only views."""
    from functools import wraps
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('is_admin'):
            return redirect('adminlogin')
        return view_func(request, *args, **kwargs)
    return wrapper

def register(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        address = request.POST.get('location')
        phone = request.POST.get('phone')
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
        else:
            user = User.objects.create(name=name, email=email, password=make_password(password), address=address, phone=phone)
            request.session['email'] = user.email   # ← log them in immediately
            request.session['name'] = user.name
            return redirect('index')
    return render(request, 'register.html')


def login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            user = User.objects.get(email=email)
            if not check_password(password, user.password):
                messages.error(request, 'Invalid email or password.')
                return render(request, 'login.html')
            request.session['email'] = user.email   # ← set session
            request.session['name'] = user.name
            return redirect('/')                     # ← redirect to / not 'index'
        except User.DoesNotExist:
            messages.error(request, 'Invalid email or password.')
    return render(request, 'login.html')


@never_cache
def profile(request):
    email = request.session.get('email')
    if email is not None:
        try:
            user = User.objects.get(email=email)
            return render(request, 'profile.html', {'user': user})
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
            return redirect('login')
    else:
        messages.error(request, 'You are not logged in.')
        return redirect('login')
    
def logout(request):
    request.session.flush()
    return redirect('/')

def editprofile(request):
    email = request.session.get('email') 
    user = User.objects.get(email=email)  # Get the User object
    if request.method == 'POST':
        # Get the form data
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        location = request.POST.get('location')
        user.name = name
        user.phone = phone
        user.address = location
        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')  
    return render(request, 'profile.html', {'user': user})

@admin_required
def userlist(request):
    user=User.objects.all()
    return render(request,'userlist.html',{'user':user})

@admin_required
def deleteuser(request,id):
    data=User.objects.filter(id=id)
    data.delete()
    return redirect('userlist')

@admin_required
def products(request):
    products = Product.objects.all().order_by('-created_at')
    categories = Category.objects.all()
    edit_product_obj = None

    # handle edit_id in GET to open edit form
    edit_id = request.GET.get('edit')
    if edit_id:
        edit_product_obj = get_object_or_404(Product, id=edit_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            Product.objects.create(
                name        = request.POST.get('name'),
                description = request.POST.get('description'),
                price       = request.POST.get('price'),
                quantity    = request.POST.get('quantity'),
                category    = request.POST.get('category'),
                image       = request.FILES.get('image'),
            )
            messages.success(request, 'Product added successfully.')
            return redirect('products')

        elif action == 'edit':
            pid = request.POST.get('product_id')
            product = get_object_or_404(Product, id=pid)
            product.name        = request.POST.get('name')
            product.description = request.POST.get('description')
            product.price       = request.POST.get('price')
            product.quantity    = request.POST.get('quantity')
            product.category    = request.POST.get('category')
            if request.FILES.get('image'):
                product.image = request.FILES.get('image')
            product.save()
            messages.success(request, f'"{product.name}" updated.')
            return redirect('products')

        elif action == 'delete':
            pid = request.POST.get('product_id')
            product = get_object_or_404(Product, id=pid)
            name = product.name
            product.delete()
            messages.success(request, f'"{name}" deleted.')
            return redirect('products')

    return render(request, 'products.html', {
        'products':          products,
        'categories':        categories,
        'edit_product_obj':  edit_product_obj,
    })


def add_to_cart(request, id):
    product = get_object_or_404(Product, id=id)
    email = request.session.get('email')
    if email:
        user = get_object_or_404(User, email=email)
        cart_item, created = Cart.objects.get_or_create(
            user=user,
            product=product,
            defaults={'quantity': 1}
        )
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        return redirect('cart')
    else:
        return redirect('login')


@never_cache
def cart(request):
    email = request.session.get('email')
    if email:
        user = get_object_or_404(User, email=email)
        cart_items = Cart.objects.filter(user=user).select_related('product')

        for item in cart_items:
            try:
                cat = Category.objects.get(name=item.product.category)
                item.is_digital = cat.is_digital
            except Category.DoesNotExist:
                item.is_digital = False
            # Stock check flag per item
            item.exceeds_stock = item.quantity > item.product.quantity
            item.stock_left = item.product.quantity

        total_price = sum(item.total_price for item in cart_items)
        total_price_int = int(total_price)

        physical_total = sum(item.total_price for item in cart_items if not item.is_digital)
        physical_total_int = int(physical_total)
        has_physical = any(not item.is_digital for item in cart_items)

        delivery_fee = 0 if (physical_total_int >= 10000 or not has_physical) else 199
        grand_total = total_price_int + delivery_fee
        delivery_remaining = max(0, 10000 - physical_total_int)

        has_stock_issue = any(item.exceeds_stock for item in cart_items)

        return render(request, 'cart.html', {
            'cart_items': cart_items,
            'total_price': total_price_int,
            'delivery_fee': delivery_fee,
            'grand_total': grand_total,
            'delivery_remaining': delivery_remaining,
            'has_stock_issue': has_stock_issue,
        })
    else:
        return redirect('login')
     
def delete_cart(request, id): 
    if request.method == "POST": 
        cart_item = get_object_or_404(Cart, id=id) 
        cart_item.delete() 
        return redirect('cart') 
    return render(request, 'cart.html')
 
 
@never_cache
def all_products(request):
    category = request.GET.get("category", "")
    
    if category:
        products = Product.objects.filter(category=category)
    else:
        products = Product.objects.all()
 
    # format prices here instead of using humanize in template
    for product in products:
        try:
            product.formatted_price = "{:,.0f}".format(float(product.price))
        except:
            product.formatted_price = product.price
 
    cart_items = []
    cart_product_ids = []
 
    email = request.session.get("email")
 
    if email:
        try:
            user = User.objects.get(email=email)
            cart_items = Cart.objects.filter(user=user)
            cart_product_ids = [item.product.id for item in cart_items]
        except User.DoesNotExist:
            pass
 
    # get all distinct categories that have products
    categories = Product.objects.values_list("category", flat=True).distinct().order_by("category")
    
    # Get active promos for banner and price display
    active_promos = Promotion.objects.filter(is_active=True)
    now = timezone.now()
    active_promos = [p for p in active_promos if p.is_valid_now]

    # Build a dict: category_name → promo for price display on cards
    category_promo_map = {}
    for promo in active_promos:
        if promo.promo_type == 'PERCENTAGE' and promo.applies_to_category:
            category_promo_map[promo.applies_to_category] = promo

    # Tag each product with its promo price if applicable
    for product in products:
        promo = category_promo_map.get(product.category)
        if promo:
            raw_discount = float(product.price) * promo.discount_percent / 100
            if promo.max_discount_amount:
                discount = min(raw_discount, float(promo.max_discount_amount))
            else:
                discount = raw_discount
            product.promo_price = round(float(product.price) - discount, 2)
            product.promo_price_formatted = "{:,.0f}".format(product.promo_price)
            product.has_promo = True
            product.promo_label = f'{promo.discount_percent}% OFF'
        else:
            product.has_promo = False

    return render(request, "all_products.html", {
        "products":          products,
        "cart_items":        cart_items,
        "cart_product_ids":  cart_product_ids,
        "categories":        categories,
        "active_category":   category,
        "active_promos":     active_promos,
        "category_promo_map": category_promo_map,
    })
    
def increase_cart(request, id):
    email = request.session.get("email")
    if not email:
        return redirect("login")
 
    referer = request.META.get('HTTP_REFERER', '')
    coming_from_cart = 'cart' in referer
 
    if coming_from_cart:
        # id is Cart item id when called from cart page
        cart_item = get_object_or_404(Cart, id=id)
        cart_item.quantity += 1
        cart_item.save()
    else:
        # id is Product id when called from all_products page
        user = User.objects.get(email=email)
        product = get_object_or_404(Product, id=id)
        cart_item, created = Cart.objects.get_or_create(
            user=user,
            product=product,
            defaults={"quantity": 1}
        )
        if not created:
            cart_item.quantity += 1
            cart_item.save()
 
    if coming_from_cart:
        return redirect("cart")
    return redirect("all_products")
 
 
def decrease_cart(request, id):
    email = request.session.get("email")
    if not email:
        return redirect("login")
 
    referer = request.META.get('HTTP_REFERER', '')
    coming_from_cart = 'cart' in referer
 
    if coming_from_cart:
        # id is Cart item id when called from cart page
        cart_item = get_object_or_404(Cart, id=id)
        if cart_item.quantity > 1:
            cart_item.quantity -= 1
            cart_item.save()
        else:
            cart_item.delete()
    else:
        # id is Product id when called from all_products page
        user = User.objects.get(email=email)
        product = get_object_or_404(Product, id=id)
        try:
            cart_item = Cart.objects.get(user=user, product=product)
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
                cart_item.save()
            else:
                cart_item.delete()
        except Cart.DoesNotExist:
            pass
 
    if coming_from_cart:
        return redirect("cart")
    return redirect("all_products")


def adminlogin(request):
    if request.method == "POST":
        uname = request.POST.get('username')
        passw = request.POST.get('password')
        
        from django.contrib.auth import authenticate
        user = authenticate(request, username=uname, password=passw)
        
        if user is not None and user.is_superuser:
            request.session['is_admin'] = True
            return redirect('adminhome')
        else:
            return render(request, 'adminlogin.html', {'error': 'Invalid credentials'})
    
    return render(request, 'adminlogin.html')
 
 
@admin_required
def adminhome(request):
    if not request.session.get('is_admin'):
        return redirect('adminlogin')
 
    total_products   = Product.objects.count()
    total_users      = User.objects.count()
    total_cart_items = Cart.objects.count()
 
    recent_products  = Product.objects.order_by('-created_at')[:6]
    recent_carts     = Cart.objects.select_related('user', 'product').order_by('-created_at')[:8]
    feedbacks        = Feedback.objects.order_by('-created_at')
    contact_messages = ContactMessage.objects.order_by('-created_at')
 
    return render(request, 'adminhome.html', {
        'total_products':   total_products,
        'total_users':      total_users,
        'total_cart_items': total_cart_items,
        'recent_products':  recent_products,
        'recent_carts':     recent_carts,
        'feedbacks':        feedbacks,
        'contact_messages': contact_messages,
    })

def adminlogout(request):
    request.session.pop('is_admin', None)
    return redirect('adminlogin')

def feedback(request):
    email = request.session.get('email')
    if not email:
        return redirect('login')
 
    user = User.objects.filter(email=email).first()
 
    if request.method == "POST":
        feedback_text = request.POST.get('feedback_text')
        rating = request.POST.get('rating')
 
        if not feedback_text or not rating:
            return JsonResponse({'status': 'error', 'message': 'Please fill in all fields.'}, status=400)
 
        try:
            rating = int(rating)
            if rating not in [1, 2, 3, 4, 5]:
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Please select a valid rating.'}, status=400)
 
        Feedback.objects.create(
            feedback_text=feedback_text,
            rating=rating,
            email=email
        )
        return JsonResponse({'status': 'ok'})
 
    return render(request, 'feedback.html', {'e': user})

def contact(request):
    if request.method == "POST":
        name    = request.POST.get('name')
        email   = request.POST.get('email')
        message = request.POST.get('message')
 
        if name and email and message:
            ContactMessage.objects.create(name=name, email=email, message=message)
 
        return JsonResponse({'status': 'ok'})
 
    return render(request, 'contact.html')

@admin_required
def category_list(request):
    categories = Category.objects.all()
    return render(request, 'categories.html', {'categories': categories})

@admin_required
def add_category(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            if Category.objects.filter(name__iexact=name).exists():
                messages.error(request, f'Category "{name}" already exists.')
            else:
                Category.objects.create(name=name)
                messages.success(request, f'Category "{name}" added successfully.')
        return redirect('category_list')
    return redirect('category_list')

@admin_required
def edit_category(request, id):
    category = get_object_or_404(Category, id=id)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            if Category.objects.filter(name__iexact=name).exclude(id=id).exists():
                messages.error(request, f'Category "{name}" already exists.')
            else:
                category.name = name
                category.save()
                messages.success(request, 'Category updated successfully.')
        return redirect('category_list')
    return redirect('category_list')

@admin_required
def delete_category(request, id):
    category = get_object_or_404(Category, id=id)
    if Product.objects.filter(category=category.name).exists():
        messages.error(request, 'Products exists in Category')
    else:
        category.delete()
        messages.success(request, f'Category "{category.name}" deleted.')
    return redirect('category_list')


@never_cache
def checkout(request):
    email = request.session.get('email')
    user  = None
    cart_items = []
    prefill    = {}

    if email:
        try:
            user = User.objects.get(email=email)
            cart_items = list(Cart.objects.filter(user=user).select_related('product'))
            prefill = {
                'full_name': user.name,
                'email':     user.email,
                'phone':     user.phone,
                'address':   user.address,
            }
        except User.DoesNotExist:
            pass

    if not cart_items:
        messages.error(request, 'Your cart is empty.')
        return redirect('cart')

    # Separate digital vs physical items
    digital_items  = []
    physical_items = []
    for item in cart_items:
        try:
            cat = Category.objects.get(name=item.product.category)
            if cat.is_digital:
                digital_items.append(item)
            else:
                physical_items.append(item)
        except Category.DoesNotExist:
            physical_items.append(item)

    has_digital  = len(digital_items)  > 0
    has_physical = len(physical_items) > 0

    # Delivery fee only on physical items
    physical_total   = sum(item.total_price for item in physical_items)
    digital_total    = sum(item.total_price for item in digital_items)
    total_price      = int(physical_total + digital_total)
    physical_total_int = int(physical_total)
    delivery_fee     = 0 if (physical_total_int >= 10000 or not has_physical) else 199
    grand_total      = total_price + delivery_fee

    if request.method == 'POST':
        full_name      = request.POST.get('full_name', '').strip()
        order_email    = request.POST.get('email', '').strip()
        phone          = request.POST.get('phone', '').strip()
        address        = request.POST.get('address', '').strip()
        city           = request.POST.get('city', '').strip()
        pincode        = request.POST.get('pincode', '').strip()
        payment_method = request.POST.get('payment_method', '')
        upi_id         = request.POST.get('upi_id', '').strip()
        card_number    = request.POST.get('card_number', '').strip()
        card_expiry    = request.POST.get('card_expiry', '').strip()
        card_cvv       = request.POST.get('card_cvv', '').strip()
        delivery_email = request.POST.get('delivery_email', '').strip()
        coupon_code    = request.POST.get('coupon_code', '').strip().upper()

        # Validate promo if entered
        discount_amount = 0
        applied_promo   = None
        free_product    = None

        if coupon_code:
            result = validate_coupon(coupon_code, cart_items)
            if result['valid']:
                discount_amount = result['discount_amount']
                applied_promo   = result['promo']
                free_product    = result['free_product']
            else:
                messages.error(request, result['error'])
                return render(request, 'checkout.html', {
                    'cart_items':     cart_items,
                    'digital_items':  digital_items,
                    'physical_items': physical_items,
                    'has_digital':    has_digital,
                    'has_physical':   has_physical,
                    'total_price':    total_price,
                    'delivery_fee':   delivery_fee,
                    'grand_total':    grand_total,
                    'prefill':        prefill,
                    'coupon_code':    coupon_code,
                })

        final_grand_total = max(0, grand_total - int(discount_amount))

        order = Order.objects.create(
            user            = user,
            full_name       = full_name,
            email           = order_email,
            phone           = phone,
            address         = address if has_physical else 'Digital Product',
            city            = city    if has_physical else 'N/A',
            pincode         = pincode if has_physical else 'N/A',
            payment_method  = payment_method,
            upi_id          = upi_id      if payment_method == 'UPI'  else None,
            card_number     = card_number if payment_method == 'CARD' else None,
            card_expiry     = card_expiry if payment_method == 'CARD' else None,
            card_cvv        = card_cvv    if payment_method == 'CARD' else None,
            delivery_email  = delivery_email if has_digital else None,
            subtotal        = total_price,
            delivery_fee    = delivery_fee,
            discount_amount = discount_amount,
            grand_total     = final_grand_total,
            promo_code      = applied_promo.coupon_code if applied_promo else None,
        )

        for item in cart_items:
            OrderItem.objects.create(
                order         = order,
                product_name  = item.product.name,
                product_image = item.product.image.url if item.product.image else '',
                price         = item.product.price,
                quantity      = item.quantity,
                is_digital    = item in digital_items,
            )
            product = item.product
            product.quantity = max(0, product.quantity - item.quantity)
            product.save()
        # Add free product as an OrderItem if applicable
        if free_product:
            OrderItem.objects.create(
                order         = order,
                product_name  = f'{free_product.name} (FREE)',
                product_image = free_product.image.url if free_product.image else '',
                price         = 0,
                quantity      = 1,
                is_digital    = False,
            )

        if user:
            Cart.objects.filter(user=user).delete()

        return redirect('order_confirmation', order_id=order.order_id)

    return render(request, 'checkout.html', {
        'cart_items':      cart_items,
        'digital_items':   digital_items,
        'physical_items':  physical_items,
        'has_digital':     has_digital,
        'has_physical':    has_physical,
        'total_price':     total_price,
        'delivery_fee':    delivery_fee,
        'grand_total':     grand_total,
        'prefill':         prefill,
    })

def order_confirmation(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    return render(request, 'order_confirmation.html', {'order': order})


def order_history(request):
    email = request.session.get('email')
    if not email:
        return redirect('login')
    orders = Order.objects.filter(email=email).prefetch_related('items')
    return render(request, 'order_history.html', {'orders': orders})


# ── Admin order views ──────────────────────────────────────────────
@admin_required
def admin_orders(request):
    orders = Order.objects.prefetch_related('items').all()
    return render(request, 'admin_orders.html', {'orders': orders})


@admin_required
def update_order_status(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['Pending', 'Processing', 'Shipped', 'Delivered']:
            order.status = new_status
            order.save()
            messages.success(request, f'Order {order.order_id} status updated to {new_status}.')
    return redirect('admin_orders')

@admin_required
def toggle_digital(request, id):
    category = get_object_or_404(Category, id=id)
    if request.method == 'POST':
        category.is_digital = not category.is_digital
        category.save()
        state = 'Digital' if category.is_digital else 'Physical'
        messages.success(request, f'"{category.name}" marked as {state}.')
    return redirect('category_list')

@admin_required
def save_license_key(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    if request.method == 'POST':
        key = request.POST.get('license_key', '').strip()
        if key:
            order.license_key = key
            order.save()
            messages.success(request, f'License key saved for order {order.order_id}.')
        else:
            messages.error(request, 'License key cannot be empty.')
    return redirect('admin_orders')

def about(request):
    return render(request, 'about.html')

def robots_txt(request):
    return HttpResponse(
        open('Overclock/templates/robots.txt').read(),
        content_type='text/plain'
    )

# ══════════════════════════════════════════════
#  PROMOTIONS
# ══════════════════════════════════════════════

from django.utils import timezone

def validate_coupon(coupon_code, cart_items):
    """
    Returns a dict with validation result and discount details.
    """
    try:
        promo = Promotion.objects.get(coupon_code__iexact=coupon_code)
    except Promotion.DoesNotExist:
        return {'valid': False, 'error': 'Invalid coupon code.'}

    if not promo.is_valid_now:
        if not promo.is_active:
            return {'valid': False, 'error': 'This coupon is not active.'}
        now = timezone.now()
        if now < promo.start_date:
            return {'valid': False, 'error': 'This coupon is not valid yet.'}
        if now > promo.end_date:
            return {'valid': False, 'error': 'This coupon has expired.'}

    # Find applicable items
    if promo.applies_to_category:
        applicable_items = [
            item for item in cart_items
            if item.product.category == promo.applies_to_category
        ]
        if not applicable_items:
            return {
                'valid': False,
                'error': f'This coupon only applies to {promo.applies_to_category}. '
                         f'None in your cart.'
            }
    else:
        applicable_items = list(cart_items)

    # Calculate discount
    if promo.promo_type == 'PERCENTAGE':
        applicable_subtotal = sum(item.total_price for item in applicable_items)
        raw_discount = applicable_subtotal * promo.discount_percent / 100
        # Apply cap if set
        if promo.max_discount_amount:
            discount_amount = min(raw_discount, promo.max_discount_amount)
        else:
            discount_amount = raw_discount
        return {
            'valid':            True,
            'promo':            promo,
            'discount_amount':  round(discount_amount, 2),
            'applicable_items': applicable_items,
            'free_product':     None,
        }

    elif promo.promo_type == 'FREE_PRODUCT':
        # Only deduct price if the free product is already in the cart
        free_product = promo.free_product
        cart_product_names = [item.product.name for item in cart_items]
        already_in_cart = free_product and free_product.name in cart_product_names

        return {
            'valid':            True,
            'promo':            promo,
            'discount_amount':  free_product.price if (free_product and already_in_cart) else 0,
            'applicable_items': applicable_items,
            'free_product':     free_product,
        }

    return {'valid': False, 'error': 'Unknown promo type.'}


# ── Admin promo views ──────────────────────────────────────────────

@admin_required
def promo_list(request):
    promos = Promotion.objects.all()
    products = Product.objects.all()
    categories = Category.objects.all()
    now = timezone.now()
    return render(request, 'promos.html', {
        'promos':     promos,
        'products':   products,
        'categories': categories,
        'now':        now,
    })


@admin_required
def add_promo(request):
    if request.method == 'POST':
        name               = request.POST.get('name', '').strip()
        description        = request.POST.get('description', '').strip()
        promo_type         = request.POST.get('promo_type', '')
        coupon_code        = request.POST.get('coupon_code', '').strip().upper()
        applies_to_category= request.POST.get('applies_to_category', '').strip()
        start_date         = request.POST.get('start_date')
        end_date           = request.POST.get('end_date')
        discount_percent   = request.POST.get('discount_percent') or None
        max_discount_amount= request.POST.get('max_discount_amount') or None
        free_product_id    = request.POST.get('free_product') or None

        if Promotion.objects.filter(coupon_code__iexact=coupon_code).exists():
            messages.error(request, f'Coupon code "{coupon_code}" already exists.')
            return redirect('promo_list')

        Promotion.objects.create(
            name                = name,
            description         = description,
            promo_type          = promo_type,
            coupon_code         = coupon_code,
            applies_to_category = applies_to_category,
            start_date          = start_date,
            end_date            = end_date,
            discount_percent    = discount_percent,
            max_discount_amount = max_discount_amount,
            free_product_id     = free_product_id,
        )
        messages.success(request, f'Promotion "{name}" created successfully.')
    return redirect('promo_list')


@admin_required
def edit_promo(request, id):
    promo = get_object_or_404(Promotion, id=id)
    if request.method == 'POST':
        promo.name                = request.POST.get('name', '').strip()
        promo.description         = request.POST.get('description', '').strip()
        promo.promo_type          = request.POST.get('promo_type', '')
        promo.coupon_code         = request.POST.get('coupon_code', '').strip().upper()
        promo.applies_to_category = request.POST.get('applies_to_category', '').strip()
        promo.start_date          = request.POST.get('start_date')
        promo.end_date            = request.POST.get('end_date')
        promo.discount_percent    = request.POST.get('discount_percent') or None
        promo.max_discount_amount = request.POST.get('max_discount_amount') or None
        promo.free_product_id     = request.POST.get('free_product') or None
        promo.save()
        messages.success(request, f'Promotion "{promo.name}" updated.')
    return redirect('promo_list')


@admin_required
def delete_promo(request, id):
    promo = get_object_or_404(Promotion, id=id)
    if request.method == 'POST':
        name = promo.name
        promo.delete()
        messages.success(request, f'Promotion "{name}" deleted.')
    return redirect('promo_list')


@admin_required
def toggle_promo(request, id):
    promo = get_object_or_404(Promotion, id=id)
    if request.method == 'POST':
        promo.is_active = not promo.is_active
        promo.save()
        state = 'Activated' if promo.is_active else 'Deactivated'
        messages.success(request, f'"{promo.name}" {state}.')
    return redirect('promo_list')


def apply_coupon(request):
    """AJAX endpoint — validates coupon and returns discount info as JSON."""
    if request.method == 'POST':
        import json
        coupon_code = request.POST.get('coupon_code', '').strip()
        email = request.session.get('email')

        cart_items = []
        if email:
            try:
                user = User.objects.get(email=email)
                cart_items = list(Cart.objects.filter(user=user).select_related('product'))
            except User.DoesNotExist:
                pass

        if not cart_items:
            return JsonResponse({'valid': False, 'error': 'Your cart is empty.'})

        result = validate_coupon(coupon_code, cart_items)

        if result['valid']:
            promo = result['promo']
            response = {
                'valid':           True,
                'promo_name':      promo.name,
                'promo_type':      promo.promo_type,
                'discount_amount': float(result['discount_amount']),
                'coupon_code':     promo.coupon_code,
            }
            if promo.promo_type == 'FREE_PRODUCT' and result['free_product']:
                response['free_product_name'] = result['free_product'].name
                response['free_product_price'] = float(result['free_product'].price)
            return JsonResponse(response)
        else:
            return JsonResponse({'valid': False, 'error': result['error']})

    return JsonResponse({'valid': False, 'error': 'Invalid request.'})

def remove_coupon(request):
    if request.method == 'POST':
        request.session.pop('applied_coupon', None)
        request.session.pop('discount_amount', None)
    return redirect('checkout')


def build_pc(request):
    return render(request, 'buildpc.html')