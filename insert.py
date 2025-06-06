import os
import django

# Set the settings module (replace 'smc_slt.settings' with your actual project settings)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smc_slt.settings")

# Initialize Django
django.setup()

import csv
from smc_slt_app.models import Product, Inventory, Package  # Adjust based on your app name

def import_products_from_csv(csv_file_path):
    with open(csv_file_path, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            # 🔹 Get the product_name ID from Inventory
            product_inventory = Inventory.objects.filter(product_name=row["product_name_id"]).first()
            
            if not product_inventory:
                print(f"❌ Product '{row['product_name_id']}' not found in Inventory!")
                continue

            # 🔹 Get the pack_name ID from Package (if provided)
            pack = Package.objects.filter(pack_name=row["pack_name_id"]).first() if row["pack_name_id"] else None

            # 🔹 Insert into Product table
            Product.objects.create(
                product_id=row["product_id"],
                product_name=product_inventory,  # ForeignKey (stores ID)
                category=row["category"],
                amount_of_events=int(row["amount_of_events"]),
                pack_name=pack  # ForeignKey (stores ID)
            )
            inventory = Inventory.objects.get(product_name=product_inventory)
            inventory.remain_quantity = Product.objects.filter(product_name=product_inventory).count()
            inventory.save()

            print(f"✅ Inserted: {row['product_id']}")

# Usage
import_products_from_csv(r"C:\Users\kevin\Desktop\Data\products.csv")
