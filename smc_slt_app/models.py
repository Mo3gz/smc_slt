from django.db import models
from datetime import date
# django.utils.timezone.now
from django.utils import timezone
# Create your models here.

class Inventory(models.Model):
    product_name = models.CharField(max_length=30, unique=True)
    remain_quantity = models.IntegerField(default=0)
    inventory_quantity = models.IntegerField()

    def __str__(self):
        return self.product_name

class Package(models.Model):
    pack_name = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.pack_name

    def product_count(self):
        return self.product_set.count()

class Product(models.Model):
    categories = [
        ('Dynamic Microphones', 'Dynamic Microphones'),
        ('Condencer', 'Condencer'),
        ('wireless Kit', 'wireless Kit'),
        ('Power Cables', 'Power Cables'),
        ('Electric Cables', 'Electric Cables'),
        ('A 56 D', 'A 56 D'),
        ('Signal Cables', 'Signal Cables'),
        ('Drum Kit', 'Drum Kit'),
        ('Accessories', 'Accessories'),
        ('Tools', 'Tools'),
        ('speaker', 'speaker'),
        ('Mixers', 'Mixers'),
        ('Speakers', 'Speakers'),
        ('Stands', 'Stands'),
        ('Equipment', 'Equipment'),
        ('Par Light', 'Par Light'),
        ('Par led', 'Par led'),
        ('Light', 'Light'),
        ('Dimmer Packs', 'Dimmer Packs'),

    ]
    product_id = models.CharField(max_length=30)
    product_name = models.ForeignKey(Inventory, on_delete=models.PROTECT)
    category = models.CharField(max_length=30, choices=categories)
    amount_of_events = models.IntegerField(default=0)
    pack_name = models.ForeignKey(Package, on_delete=models.PROTECT, null=True, blank=True)

    def __str__(self):
        return self.product_id

class Event(models.Model):
    event_code = models.AutoField(primary_key=True)
    event_name = models.CharField(max_length=30)
    leader_name = models.CharField(max_length=30)
    wh_leader = models.CharField(max_length=30)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=None, null=True, blank=True)

    def __str__(self):
        return str(self.event_code)

class Order(models.Model):
    choices = [
        ('add', 'add'),
        ('recovery', 'recovery'),
    ]
    event_code = models.ForeignKey(Event, on_delete=models.PROTECT)
    product_id = models.CharField(max_length=30)
    state = models.CharField(max_length=10, choices=choices, default='add')

    def __str__(self):
        return f"{self.product_id} {str(self.event_code)}"

class Maintenance(models.Model):
    choices = [
        ('Pending','Pending'),
        ('Good','Good'),
        ('Failed','Failed')
    ]
    product_id = models.CharField(max_length=30)
    damage_date = models.DateField(default=timezone.now)
    maint_date = models.DateField(default=None, null=True, blank=True)
    description = models.TextField(default=None)
    delivered_by = models.CharField(default=None, max_length=30)
    received_by = models.CharField(default=None, max_length=30, null=True, blank=True)
    event_code = models.CharField(default=None, max_length=30)
    status = models.CharField(max_length=10, choices=choices, default='Pending', blank=True)

    def __str__(self):
        return self.product_id


