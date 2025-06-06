from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models.deletion import ProtectedError
from datetime import date
from .models import *
from .forms import *
from members.models import CustomUser
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.core.mail import send_mail
from django.core.mail import EmailMessage
from django.urls import reverse
from django.db.models import Case, When, IntegerField, Value


# ======================================= Helpers ==================================================

def update_inventory(product_id, quantity_change):
    parent = Product.objects.get(product_id=product_id).product_name
    inventory = Inventory.objects.get(product_name=parent)
    inventory.remain_quantity += quantity_change
    inventory.save()

def get_invoice_context(event_code, user=None):
    event_details = get_object_or_404(Event, event_code=event_code)
    event_orders = Order.objects.filter(event_code=event_code, state='add')
    event_returns = Order.objects.filter(event_code=event_code, state='recovery')

    add_product_names = [Product.objects.get(product_id=order.product_id).product_name for order in event_orders]
    return_product_names = [Product.objects.get(product_id=order.product_id).product_name for order in event_returns]

    add_zipped_orders = zip(set(add_product_names), [add_product_names.count(name) for name in set(add_product_names)])
    return_zipped_orders = zip(set(return_product_names), [return_product_names.count(name) for name in set(return_product_names)])

    context = {
        'eventdetails': event_details,
        'eventorders': add_zipped_orders,
        'eventreturns': return_zipped_orders,
        'returnsorder': event_returns,
        'user': user
    }
    return context
# ======================================= Product Functions ==================================================

def page_list_product(request):
    query = request.GET.get('q', '').strip()
    
    # Ensure we are filtering by the correct field in the related model
    product_list = Product.objects.filter(product_id__icontains=query).order_by('id') 
    
    # Get the page size from the request, defaulting to 50 if not specified
    page_size = request.GET.get('page_size', 10)
    
    paginator = Paginator(product_list, page_size)  # Use the selected page size

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    page_sizes = [10, 25, 50, 100]
    
    context = {
        'page_obj': page_obj,
        'page_size': int(page_size),  # Convert to int for comparison in the template
        'page_sizes': page_sizes,
        'query': query
    }
    return render(request, 'pages/page-list-product.html', context)

def page_add_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            inventory = Inventory.objects.get(product_name=form.cleaned_data['product_name'])
            if inventory.remain_quantity == inventory.inventory_quantity:
                messages.warning(request, "You Can't Add More Devices")
            else:
                product = form.save()
                inventory.remain_quantity = Product.objects.filter(product_name=product.product_name).count()
                inventory.save()
                return redirect('/page-add-product')
        else:
            messages.warning(request, "This Device Was Exist!")
    context = {'productform': ProductForm()}
    return render(request, 'pages/page-add-product.html', context)

def page_update_product(request, id):
    product = get_object_or_404(Product, id=id)

    # Check if product is in an event
    last_order = Order.objects.filter(product_id=product).last()
    if last_order and last_order.state == 'add':
        messages.warning(request, "This Product is in an Event.")
        return redirect('/page-list-product')

    # Check if product is in maintenance with status 'Pending'
    maintenance_entries = Maintenance.objects.filter(product_id=product)
    if maintenance_entries.exists() and maintenance_entries.last().status == 'Pending':
        messages.warning(request, "This Device is under Maintenance.")
        return redirect('/page-list-product')

    # Handle POST or display form
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            # Avoid duplicate product_id (excluding current one)
            if Product.objects.filter(product_id=form.cleaned_data['product_id']).exclude(id=product.id).exists():
                messages.warning(request, "This Device ID already exists!")
            else:
                form.save()
                return redirect('/page-list-product')
        else:
            messages.warning(request, "Please correct the errors below.")
    else:
        form = ProductForm(instance=product)
        form.fields['product_name'].widget.attrs.update({'class': 'form-control', 'readonly': 'True'})

    context = {'productform': form, 'product_name': product.product_name.product_name}
    return render(request, 'pages/page-update-product.html', context)

def page_view_product(request, id):
    context = {'productform': get_object_or_404(Product, id=id)}
    return render(request, 'pages/page-view-product.html', context)

def page_delete_product(request, id):
    product = get_object_or_404(Product, id=id)
    if request.method == 'POST':
        filtered_result = Order.objects.filter(product_id=product.product_id).last()
        status = [m.status for m in Maintenance.objects.filter(product_id=product.product_id)]
        if filtered_result and filtered_result.state == 'add':
            messages.warning(request, "This Device In Event")
        elif product.product_id in [p.product_id for p in Maintenance.objects.all()] and status[-1] == 'Pending':
            messages.warning(request, "This Device In Maintenance")
        else:
            update_inventory(product.product_id, -1)
            product.delete()
        return redirect('/page-list-product')
    return render(request, 'pages/page-delete-product.html')

# ======================================= Inventory Functions ==================================================

def page_list_inventory(request):
    query = request.GET.get('q', '').strip()
    
    # Filter the inventory list based on the search query
    inventory_list = Inventory.objects.filter(product_name__icontains=query).order_by('id')
    
    # Get the page size from the request, defaulting to 50 if not specified
    page_size = request.GET.get('page_size', 10)
    
    paginator = Paginator(inventory_list, page_size)  # Use the selected page size

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    page_sizes = [10, 25, 50, 100]
    
    context = {
        'page_obj': page_obj,
        'page_size': int(page_size),  # Convert to int for comparison in the template
        'page_sizes': page_sizes,
        'query': query
    }
    return render(request, 'pages/page-list-inventory.html', context)

def page_add_inventory(request):
    if request.method == 'POST':
        form = InventoryForm(request.POST)
        if not request.POST.get('product_name', '').strip():
            messages.warning(request, 'Fields cannot be empty or only contain spaces.')
        elif form.is_valid():
            form.save()
        else:
            messages.warning(request, "This Inventory is Already Exist")
        return redirect('/page-add-inventory')
    context = {'inventoryform': InventoryForm()}
    return render(request, 'pages/page-add-inventory.html', context)

def page_update_inventory(request, id):
    inventory = get_object_or_404(Inventory, id=id)
    if request.method == 'POST':
        form = InventoryForm(request.POST, instance=inventory)
        if form.is_valid():
            if inventory.inventory_quantity < inventory.remain_quantity:
                messages.warning(request, "This Quantity Less Than Devices")
                return redirect(f'/update-inventory-{id}')
            else:
                form.save()
                return redirect('/page-list-inventory')
        return redirect('/page-list-inventory')
    context = {'inventoryform': InventoryForm(instance=inventory)}
    return render(request, 'pages/page-update-inventory.html', context)

def page_delete_inventory(request, id):
    inventory = get_object_or_404(Inventory, id=id)
    if request.method == 'POST':
        try:
            inventory.delete()
            return redirect('/page-list-inventory')
        except ProtectedError:
            messages.warning(request, "You Should Delete All Devices In Products Tab First.")
    return render(request, 'pages/page-delete-inventory.html')

def page_view_inventory(request, id):
    context = {'inventoryform': get_object_or_404(Inventory, id=id)}
    return render(request, 'pages/page-view-inventory.html', context)

# ======================================= Event Functions ==================================================

def page_add_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if not all(request.POST.get(field, '').strip() for field in ['event_name', 'leader_name', 'wh_leader']):
            messages.warning(request, 'Fields cannot be empty or only contain spaces.')
        elif form.is_valid():
            event = form.save()
            return redirect(f'/add-order-{event.event_code}')  # Redirect to add-order page with event_code

    context = {'eventform': EventForm()}
    return render(request, 'pages/page-add-event.html', context)


def page_list_event(request):
    query = request.GET.get('q', '').strip()

    # Custom ordering: Events with NULL end_date come first
    event_list = Event.objects.filter(event_name__icontains=query).annotate(
        end_date_order=Case(
            When(end_date__isnull=True, then=Value(0)),  # Events without an end date first
            default=Value(1),  # Events with an end date last
            output_field=IntegerField(),
        )
    ).order_by('end_date_order', '-event_code')  # Sort by end_date_order first, then by event_code

    # Get the page size from the request, default to 10 if not specified
    page_size = request.GET.get('page_size', 10)

    paginator = Paginator(event_list, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    page_sizes = [10, 25, 50, 100]

    context = {
        'page_obj': page_obj,
        'page_size': int(page_size),
        'page_sizes': page_sizes,
        'query': query
    }
    return render(request, 'pages/page-list-event.html', context)

def page_update_event(request, event_code):
    event = get_object_or_404(Event, event_code=event_code)
    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            return redirect('/page-list-event')
        return redirect('/page-list-event')
    context = {'eventform': EventForm(instance=event)}
    return render(request, 'pages/page-update-event.html', context)

def page_delete_event(request, event_code):
    event = get_object_or_404(Event, event_code=event_code)
    if request.method == 'POST':
        try:
            event.delete()
            return redirect('/page-list-event')
        except ProtectedError:
            messages.warning(request, "Delete Orders Inside Event First")
    return render(request, 'pages/page-delete-event.html')

# ======================================= Order Functions ==================================================

def page_add_order(request, event_code):

    event = get_object_or_404(Event, event_code=event_code)
    if event.end_date is not None:
        messages.warning(request, 'This Event Was End')
        return redirect('/page-list-event')

    # Retrieve search query from GET request
    query = request.GET.get('q', '').strip()
    
    # Filter orders based on the query
    orders = Order.objects.filter(event_code=event_code, state='add')
    if query:
        orders = orders.filter(product_id__icontains=query)

    if request.method == 'POST':
        selected_products = request.POST.getlist('selected_products')
        if selected_products:
            product_count = int(request.POST.get('product_count', 0))
            state, fail_names, succ_names = [], [], []
            for product in selected_products:
                filtered_result = Order.objects.filter(product_id=product).last()
                status = [m.status for m in Maintenance.objects.filter(product_id=product)]
                if filtered_result and filtered_result.state == 'add': # Sure that device exist in my event or another event
                    if event == filtered_result.event_code:
                        state.append(True)
                    else:
                        fail_names.append(filtered_result.product_id)
                        state.append(False)
                elif Maintenance.objects.filter(product_id=product).exists() and status[-1] == 'Pending':
                    messages.warning(request, f"This {product} In Maintenance")
                else:
                    succ_names.append(product)
                    Order.objects.create(product_id=product, event_code=event, state='add')
                    update_inventory(product, -1)
            if len(selected_products) == 1:
                if state == []:
                    messages.success(request, f"{product} Added succeffully")
                elif state[0] == False:
                    messages.warning(request, f"{product} In Another Event!")
                elif state[0] == True:
                    messages.warning(request, f"{product} Already Exist!")
            elif all(state) and len(state) == product_count:
                messages.warning(request, "Package is Already Added Before")
            elif all(state) and len(state) + len(succ_names) == len(selected_products):
                messages.success(request, f"Package is Added successfully")
            elif all((not item for item in state)) and len(state) == product_count:
                messages.warning(request, "This Package In Another Event")
            else:
                for name in fail_names:
                        messages.warning(request, f"{name} In Another Event")
                for name in succ_names:
                    messages.success(request, f"{name} Added successfully")
                

            return redirect(f'/add-order-{event_code}')

        form = OrderForm(request.POST)
        if not all(request.POST.get(field, '').strip() for field in ['event_code', 'product_id']):
            messages.warning(request, 'Fields cannot be empty or only contain spaces.')
        elif form.is_valid():
            product_name = form.cleaned_data['product_id']
            if not Product.objects.filter(product_id=product_name).exists() and not Package.objects.filter(pack_name=product_name).exists():
                messages.warning(request, "This Device ID Doesn't Exist")
            else:
                filtered_result = Order.objects.filter(product_id=product_name).last()
                status = [m.status for m in Maintenance.objects.filter(product_id=product_name)]
                if Order.objects.filter(event_code=event_code, state='add', product_id=product_name).exists():
                    messages.warning(request, "This Device Was Added")
                elif Package.objects.filter(pack_name=product_name).exists():
                    package = Package.objects.filter(pack_name=product_name).first()
                    if package:
                        products_in_package = Product.objects.filter(pack_name=package)
                        product_count = Product.objects.filter(pack_name=package).count()
                        if not products_in_package:
                            messages.warning(request, "This Package is Empty")
                        else:
                            context = {
                                'products_in_package': products_in_package,
                                'orderform': form,
                                'orders': Order.objects.filter(event_code=event_code, state='add'),
                                'event_code': event_code,
                                'product_count': product_count
                            }
                            return render(request, 'pages/page-add-order.html', context)
                    else:
                        messages.warning(request, "No package found with this name")
                elif filtered_result and filtered_result.state == 'add':
                    messages.warning(request, "This Device In Another Event")
                elif Maintenance.objects.filter(product_id=product_name).exists() and status[-1] == 'Pending':
                    messages.warning(request, f"This {product_name} In Maintenance")
                else:
                    form.save()
                    update_inventory(product_name, -1)
                    return redirect(f'/add-order-{event_code}')
            return redirect(f'/add-order-{event_code}')
        return redirect(f'/add-order-{event_code}')


    returned_orders = set(Order.objects.filter(event_code=event_code, state='recovery').values_list('product_id', flat=True))
    add_order = OrderForm(initial={'event_code': event_code, 'state': 'add'})
    context = {
        'orderform': add_order,
        'orders': orders,
        'returned_orders': returned_orders,  # Pass returned orders separately
        'event_code': event_code,
        'query' : query,
    }
    return render(request, 'pages/page-add-order.html', context)

def delete_product_order(request, id):
    product_delete = get_object_or_404(Order, id=id)
     # Prevent deletion if the product is already returned
    if product_delete.state == 'recovery':
        messages.warning(request, "This device is already returned and cannot be deleted.")
        return redirect(f'/add-order-{product_delete.event_code}')

    if request.method == 'POST':
        product_delete.delete()
        update_inventory(product_delete.product_id, 1)
        return redirect(f'/add-order-{product_delete.event_code}')
    return render(request, 'pages/page-delete-order.html')

def invoice_page(request, event_code):
    if Order.objects.filter(event_code=event_code).count() == 0:
        messages.warning(request, "This Event is Empty!")
        return redirect('/page-list-event')

    event_details = get_object_or_404(Event, event_code=event_code)
    event_orders = Order.objects.filter(event_code=event_code, state='add')
    event_returns = Order.objects.filter(event_code=event_code, state='recovery')
    
    add_product_names = [Product.objects.get(product_id=order.product_id).product_name for order in event_orders]
    return_product_names = [Product.objects.get(product_id=order.product_id).product_name for order in event_returns]

    add_zipped_orders = zip(set(add_product_names), [add_product_names.count(name) for name in set(add_product_names)])
    return_zipped_orders = zip(set(return_product_names), [return_product_names.count(name) for name in set(return_product_names)])

    context = {
        'eventdetails': event_details,
        'eventorders': add_zipped_orders,
        'eventreturns': return_zipped_orders,
        'returnsorder': event_returns
    }
    return render(request, 'pages/pages-invoice.html', context)

def print_invoice(request, event_code):
    context = get_invoice_context(event_code, request.user)
    return render(request, "pages/invoice_pdf.html", context)

def page_return_order(request, event_code):
    product_choices = [('', 'Select a product')] + [(product.product_id, product.product_id) for product in Order.objects.filter(event_code=event_code, state='add')]
    if Event.objects.get(event_code=event_code).end_date is not None:
        messages.warning(request, 'This Event Was End')
        return redirect('/page-list-event')
    
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            product_id = form.cleaned_data['product_id']
            if Order.objects.filter(event_code=event_code, state='recovery', product_id=product_id).exists():
                messages.warning(request, "This Device Was Returned")
            else:
                form.save()
                update_inventory(product_id, 1)
                product = Product.objects.get(product_id=product_id)
                product.amount_of_events += 1
                product.save()
                if sorted([order.product_id for order in Order.objects.filter(event_code=event_code, state='add')]) == \
                   sorted([order.product_id for order in Order.objects.filter(event_code=event_code, state='recovery')]):
                    event = Event.objects.get(event_code=event_code)
                    event.end_date = date.today()
                    event.save()
            return redirect(f'/return-order-{event_code}')
        return redirect(f'/return-order-{event_code}')
    else:
        form = OrderForm(initial={'event_code': event_code, 'state': 'recovery'})
        form.fields['product_id'].widget = forms.Select(attrs={'class': 'form-control'})  # Change to Select field
        form.fields['product_id'].widget.choices = product_choices  # Set available choices


    context = {
        'returnform': form,
        'orders': Order.objects.filter(event_code=event_code, state='add'),
        'returnorders': Order.objects.filter(event_code=event_code, state='recovery')
    }
    return render(request, 'pages/page-return-order.html', context)

# ======================================= Maintenance Functions ==================================================

def page_add_maint(request):
    if request.method == 'POST':
        form = MaintForm(request.POST)
        try:
            if not all(request.POST.get(field, '').strip() for field in ['event_code', 'product_id', 'delivered_by', 'damage_date', 'description']):
                messages.warning(request, 'Fields cannot be empty or only contain spaces.')
            elif form.is_valid():
                product_id = form.cleaned_data['product_id']
                if not Product.objects.filter(product_id=product_id).exists():
                    messages.warning(request, "This Device ID Doesn't Exist")
                elif not Event.objects.filter(event_code=form.cleaned_data['event_code']).exists():
                    messages.warning(request, "This Event Code Doesn't Exist")
                else:
                    filtered_result = Order.objects.filter(product_id=product_id).last()
                    status = [m.status for m in Maintenance.objects.filter(product_id=product_id)]

                    if Order.objects.filter(product_id=product_id).exists() and filtered_result and filtered_result.state == 'add':
                        messages.warning(request, "This Device In Event")
                    elif status and status[-1] == 'Pending':
                        messages.warning(request, "This Device Was Added")
                    else:
                        form.save()
                        update_inventory(product_id, -1)

                        # ✅ Send Email Notification
                        maintenance_url = request.build_absolute_uri(reverse('page_list_maint'))  # Change 'page_list_maint' to the correct view name
                        subject = "New Maintenance Added"
                        recipient_emails = ["kevinremon1234@gmail.com", "Paulagirgis123@gmail.com"]  # Change to the target email
                        message = message = f"""
                        <html>
                        <body>
                            <h2>Maintenance required for {product_id}</h2>
                            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                                <tr>
                                    <th style="background-color: #f2f2f2;">Attribute</th>
                                    <th style="background-color: #f2f2f2;">Value</th>
                                </tr>
                                <tr>
                                    <td><strong>Product ID</strong></td>
                                    <td>{product_id}</td>
                                </tr>
                                <tr>
                                    <td><strong>Event Code</strong></td>
                                    <td>{form.cleaned_data['event_code']}</td>
                                </tr>
                                <tr>
                                    <td><strong>Description</strong></td>
                                    <td>{form.cleaned_data['description']}</td>
                                </tr>
                                <tr>
                                    <td><strong>Delivered By</strong></td>
                                    <td>{form.cleaned_data['delivered_by']}</td>
                                </tr>
                                <tr>
                                    <td><strong>Damage Date</strong></td>
                                    <td>{form.cleaned_data['damage_date']}</td>
                                </tr>
                                <tr>
                                    <td><strong>Maintenance Link</strong></td>
                                    <td><a href="{maintenance_url}" target="_blank">View Maintenance Records</a></td>
                                </tr>
                            </table>
                        </body>
                        </html>
                        """

                        email = EmailMessage(subject, message, 'smc.slt2025@gmail.com', recipient_emails)
                        email.content_subtype = "html"  # Set content to HTML
                        email.send()

                    return redirect('/page-add-maint')
            return redirect('/page-add-maint')
        except ValueError:
            messages.warning(request, "Event Code Must Be Number")

    else:
        form = MaintForm()
    context = {'maintform': form}
    return render(request, 'pages/page-add-maint.html', context)


def add_product_maint(request, event_code, id, product_name):
    product_order = get_object_or_404(Order, id=id)

    # Prevent adding to maintenance if the product is already returned
    if product_order.state == 'recovery':
        messages.warning(request, "This device is already returned and cannot be added to maintenance.")
        return redirect(f'/add-order-{event_code}')
        
    if request.method == 'POST':
        form = MaintForm(request.POST)
        if not all(request.POST.get(field, '').strip() for field in ['event_code', 'product_id', 'delivered_by', 'damage_date', 'description']):
            messages.warning(request, 'Fields cannot be empty or only contain spaces.')
        elif form.is_valid():
            product_id = form.cleaned_data['product_id']
            if not Product.objects.filter(product_id=product_id).exists():
                messages.warning(request, "This Device ID Doesn't Exist")
            elif not Event.objects.filter(event_code=form.cleaned_data['event_code']).exists():
                messages.warning(request, "This Event Code Doesn't Exist")
            else:
                filtered_result = Order.objects.filter(product_id=product_id).last()
                status = [m.status for m in Maintenance.objects.filter(product_id=product_id)]

                # if Order.objects.filter(product_id=product_id).exists() and filtered_result and filtered_result.state == 'add':
                #     messages.warning(request, "This Device In Event")
                if status and status[-1] == 'Pending':
                    messages.warning(request, "This Device Was Added")
                else:
                    form.save()
                    product_delete = get_object_or_404(Order, id=id)
                    product_delete.delete()
                    product = Product.objects.get(product_id=product_delete.product_id)
                    product.amount_of_events += 1
                    product.save()
                    if sorted([order.product_id for order in Order.objects.filter(event_code=event_code, state='add')]) == \
                    sorted([order.product_id for order in Order.objects.filter(event_code=event_code, state='recovery')]):
                        event = Event.objects.get(event_code=event_code)
                        event.end_date = date.today()
                        event.save()

                    # ✅ Send Email Notification
                    maintenance_url = request.build_absolute_uri(reverse('page_list_maint'))  # Change 'page_list_maint' to the correct view name
                    subject = "New Maintenance Added"
                    recipient_emails = ["kevinremon1234@gmail.com", "Paulagirgis123@gmail.com"]  # Change to the target email
                    message = message = f"""
                    <html>
                    <body>
                        <h2>Maintenance required for {product_id}</h2>
                        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                            <tr>
                                <th style="background-color: #f2f2f2;">Attribute</th>
                                <th style="background-color: #f2f2f2;">Value</th>
                            </tr>
                            <tr>
                                <td><strong>Product ID</strong></td>
                                <td>{product_id}</td>
                            </tr>
                            <tr>
                                <td><strong>Event Code</strong></td>
                                <td>{form.cleaned_data['event_code']}</td>
                            </tr>
                            <tr>
                                <td><strong>Description</strong></td>
                                <td>{form.cleaned_data['description']}</td>
                            </tr>
                            <tr>
                                <td><strong>Delivered By</strong></td>
                                <td>{form.cleaned_data['delivered_by']}</td>
                            </tr>
                            <tr>
                                <td><strong>Damage Date</strong></td>
                                <td>{form.cleaned_data['damage_date']}</td>
                            </tr>
                            <tr>
                                <td><strong>Maintenance Link</strong></td>
                                <td><a href="{maintenance_url}" target="_blank">View Maintenance Records</a></td>
                            </tr>
                        </table>
                    </body>
                    </html>
                    """

                    email = EmailMessage(subject, message, 'smc.slt2025@gmail.com', recipient_emails)
                    email.content_subtype = "html"  # Set content to HTML
                    email.send()

                return redirect('/page-list-maint')
        return redirect(f'/add-maint-{event_code}-{product_name}')
    else:
        form = MaintForm(initial={'event_code':event_code, 'product_id':product_name})
        form.fields['event_code'].widget.attrs.update({'class': 'form-control', 'readonly': 'True'})
        form.fields['product_id'].widget.attrs.update({'class': 'form-control', 'readonly': 'True'})

    context = {'maintform': form}
    return render(request, 'pages/page-add-maint.html', context)


def return_maint(request, id):
    maint_instance = get_object_or_404(Maintenance, id=id)
    
    if maint_instance.maint_date is not None:
        messages.warning(request, "This Device Already Returned!")
        return redirect('/page-list-maint')

    if request.method == 'POST':
        form = ReturnMaintForm(request.POST, instance=maint_instance)
        if form.is_valid():
            if not all([maint_instance.status, maint_instance.received_by, maint_instance.maint_date]):
                messages.warning(request, "You Should Fill All Fields")
            elif maint_instance.status == 'Pending':
                messages.warning(request, "Change Status From Pending to Good or Failed")
            else:
                product_name = maint_instance.product_id
                if maint_instance.status == 'Good':
                    update_inventory(product_name, 1)  # The Device returned to inventory

                    # ✅ Send Email Notification
                    maintenance_url = request.build_absolute_uri(reverse('page_list_maint'))  # Change 'page_list_maint' to the correct view name
                    subject = "Item Maintenance Update"
                    recipient_emails = ["kevinremon1234@gmail.com", "Paulagirgis123@gmail.com"]  # Change to the target email
                    message = f"""
                    <html>
                    <body>
                        <h2>{product_name} has been successfully maintained and returned to inventory.</h2>
                        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                            <tr>
                                <th style="background-color: #f2f2f2;">Attribute</th>
                                <th style="background-color: #f2f2f2;">Value</th>
                            </tr>
                            <tr>
                                <td><strong>Product ID</strong></td>
                                <td>{product_name}</td>
                            </tr>
                            <tr>
                                <td><strong>Event Code</strong></td>
                                <td>{maint_instance.event_code}</td>
                            </tr>
                            <tr>
                                <td><strong>Description</strong></td>
                                <td>{maint_instance.description}</td>
                            </tr>
                            <tr>
                                <td><strong>Delivered By</strong></td>
                                <td>{maint_instance.delivered_by}</td>
                            </tr>
                            <tr>
                                <td><strong>Damage Date</strong></td>
                                <td>{maint_instance.damage_date}</td>
                            </tr>
                            <tr>
                                <td><strong>Maintenance Link</strong></td>
                                <td><a href="{maintenance_url}" target="_blank">View Maintenance Records</a></td>
                            </tr>
                        </table>
                    </body>
                    </html>
                    """

                    email = EmailMessage(subject, message, 'smc.slt2025@gmail.com', recipient_emails)
                    email.content_subtype = "html"  # Set content to HTML
                    email.send()

                elif maint_instance.status == 'Failed':
                    Product.objects.filter(product_id=product_name).delete()  # The Product is damaged

                    # ✅ Send Email Notification
                    maintenance_url = request.build_absolute_uri(reverse('page_list_maint'))  # Change 'page_list_maint' to the correct view name
                    subject = "Item Maintenance Update"
                    recipient_emails = ["kevinremon1234@gmail.com", "Paulagirgis123@gmail.com"]  # Change to the target email
                    message = f"""
                    <html>
                    <body>
                        <h2>{product_name} is a total loss and has been removed from the inventory.</h2>
                        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                            <tr>
                                <th style="background-color: #f2f2f2;">Attribute</th>
                                <th style="background-color: #f2f2f2;">Value</th>
                            </tr>
                            <tr>
                                <td><strong>Product ID</strong></td>
                                <td>{product_name}</td>
                            </tr>
                            <tr>
                                <td><strong>Event Code</strong></td>
                                <td>{maint_instance.event_code}</td>
                            </tr>
                            <tr>
                                <td><strong>Description</strong></td>
                                <td>{maint_instance.description}</td>
                            </tr>
                            <tr>
                                <td><strong>Delivered By</strong></td>
                                <td>{maint_instance.delivered_by}</td>
                            </tr>
                            <tr>
                                <td><strong>Damage Date</strong></td>
                                <td>{maint_instance.damage_date}</td>
                            </tr>
                            <tr>
                                <td><strong>Maintenance Link</strong></td>
                                <td><a href="{maintenance_url}" target="_blank">View Maintenance Records</a></td>
                            </tr>
                        </table>
                    </body>
                    </html>
                    """

                    email = EmailMessage(subject, message, 'smc.slt2025@gmail.com', recipient_emails)
                    email.content_subtype = "html"  # Set content to HTML
                    email.send()

                form.save()
                # Debugging: Check the value of maint_date after saving the form
                return redirect('/page-list-maint')  # Redirect to a different page after successful update
        return redirect(f'/return-maint-{id}')
    else:
        form = ReturnMaintForm(instance=maint_instance)
    context = {'form': form, 'maint_instance': maint_instance}
    return render(request, 'pages/return-maint.html', context)


def page_list_maint(request):
    query = request.GET.get('q', '').strip()

    # Annotate custom ordering: Pending → 1 (Highest Priority), Good → 2, Failed → 3
    maint_list = Maintenance.objects.filter(product_id__icontains=query).annotate(
        status_order=Case(
            When(status='Pending', then=1),
            When(status='Good', then=2),
            When(status='Failed', then=3),
            default=4,  # Any other status
            output_field=IntegerField(),
        )
    ).order_by('status_order', '-id')  # Sort by status order first, then by latest ID

    # Get the page size from the request, defaulting to 50 if not specified
    page_size = request.GET.get('page_size', 10)

    paginator = Paginator(maint_list, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    page_sizes = [10, 25, 50, 100]

    context = {
        'page_obj': page_obj,
        'page_size': int(page_size),
        'page_sizes': page_sizes,
        'query': query
    }
    return render(request, 'pages/page-list-maint.html', context)

    
def page_delete_maint(request, id):
    maint = get_object_or_404(Maintenance, id=id)
    if request.method == 'POST':
        if maint.status in ['Good', 'Failed']:
            maint.delete()
        else:
            maint.delete()
            update_inventory(maint.product_id, 1)
        return redirect('/page-list-maint')
    return render(request, 'pages/page-delete-maint.html')

# ======================================= Reports Functions ==================================================

def page_product_report(request):
    query = request.GET.get('q', '')
    
    # Filter the products report list based on the search query
    products_report_list = Product.objects.filter(product_id__icontains=query).order_by('id') 
    
    # Get the page size from the request, defaulting to 50 if not specified
    page_size = request.GET.get('page_size', 10)
    
    paginator = Paginator(products_report_list, page_size)  # Use the selected page size

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    page_sizes = [10, 25, 50, 100]
    
    context = {
        'page_obj': page_obj,
        'page_size': int(page_size),  # Convert to int for comparison in the template
        'page_sizes': page_sizes,
        'query': query
    }
    return render(request, 'pages/page-product-report.html', context)

def page_inventory_report(request):
    query = request.GET.get('q', '')
    
    # Filter the inventory report list based on the search query
    inventory_report_list = Inventory.objects.filter(product_name__icontains=query).order_by('id') 
    
    # Get the page size from the request, defaulting to 50 if not specified
    page_size = request.GET.get('page_size', 10)
    
    paginator = Paginator(inventory_report_list, page_size)  # Use the selected page size

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    page_sizes = [10, 25, 50, 100]
    
    context = {
        'page_obj': page_obj,
        'page_size': int(page_size),  # Convert to int for comparison in the template
        'page_sizes': page_sizes,
        'query': query
    }
    return render(request, 'pages/page-inventory-report.html', context)

def search_for_device(request, id):
    product = get_object_or_404(Product, id=id)
    product_name = product.product_id
    filtered_result = Order.objects.filter(product_id=product_name).last()
    status = [m.status for m in Maintenance.objects.filter(product_id=product)]


    if Maintenance.objects.filter(product_id=product).exists() and status[-1] == 'Pending':
        place = "This Device In Maintenance"
    elif filtered_result is None or filtered_result.state != "add":
        place = "This Device In Inventory"
    else:
        place = f"This Device In Event Has Code: {filtered_result.event_code}"

    context = {'place': place, 'product_name': product_name}
    return render(request, 'pages/search-for-device.html', context)

# ======================================= Users Functions ==================================================

def page_list_users(request):
    query = request.GET.get('q', '').strip()
    
    # Filter the user list based on the search query
    user_list = CustomUser.objects.filter(username__icontains=query).order_by('id') 
    
    # Get the page size from the request, defaulting to 50 if not specified
    page_size = request.GET.get('page_size', 10)
    
    paginator = Paginator(user_list, page_size)  # Use the selected page size

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    page_sizes = [10, 25, 50, 100]
    
    context = {
        'page_obj': page_obj,
        'page_size': int(page_size),  # Convert to int for comparison in the template
        'page_sizes': page_sizes,
        'query': query
    }
    return render(request, 'pages/page-list-users.html', context)

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {'page_obj': page_obj}
    return render(request, 'pages/page-list-users.html', context)

# ======================================= Package Functions ==================================================

def page_add_package(request):
    if request.method == 'POST':
        form = PackageForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('/page-add-package')
        else:
            messages.warning(request, "This Pack Name Was Exist")
    context = {'packageform': PackageForm()}
    return render(request, 'pages/page-add-package.html', context)

def page_list_package(request):
    query = request.GET.get('q', '').strip()
    
    # Filter the package list based on the search query
    package_list = Package.objects.filter(pack_name__icontains=query).order_by('id') 
    
    # Get the page size from the request, defaulting to 50 if not specified
    page_size = request.GET.get('page_size', 10)
    
    paginator = Paginator(package_list, page_size)  # Use the selected page size

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    page_sizes = [10, 25, 50, 100]
    
    context = {
        'page_obj': page_obj,
        'page_size': int(page_size),  # Convert to int for comparison in the template
        'page_sizes': page_sizes,
        'query': query
    }
    return render(request, 'pages/page-list-package.html', context)

def page_update_package(request, id):
    package = get_object_or_404(Package, id=id)
    if request.method == 'POST':
        form = PackageForm(request.POST, instance=package)
        if form.is_valid():
            form.save()
            return redirect('/page-list-package')
    context = {'packform': PackageForm(instance=package)}
    return render(request, 'pages/page-update-package.html', context)


def delete_package(request, id):
    try:
        pack_delete = get_object_or_404(Package, id=id)
        if request.method == 'POST':
            pack_delete.delete()
            return redirect('/page-list-package')
    except ProtectedError:
        messages.warning(request, "Delete Products Inside Package First")
    return render(request, 'pages/page-delete-package.html')

