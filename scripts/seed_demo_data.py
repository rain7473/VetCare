"""Siembra datos de demostración en Oracle (COMMIT real).

Idempotente: si ya hay propietarios/productos, no duplica el lote demo
marcado con prefijos DEMO-. Crea usuario ``demo`` / ``Demo1234`` (ADMIN)
si no existe.

    python -m scripts.seed_demo_data
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from database.connection import connection_scope
from repositories import (
    appointment_repository,
    inventory_repository,
    owner_repository,
    pet_repository,
    role_repository,
    sales_repository,
    species_repository,
    user_repository,
)
from repositories.inventory_repository import insert_lot, insert_movement, insert_product
from utils.security import hash_password


DEMO_PASSWORD = "Demo1234"


def _ensure_user(conn, *, username: str, full_name: str, role_name: str) -> int:
    existing = user_repository.find_auth_by_username(conn, username)
    role_id = role_repository.get_role_id_by_name(conn, role_name)
    if role_id is None:
        raise RuntimeError(f"Rol {role_name} no encontrado")
    pwd = hash_password(DEMO_PASSWORD)
    if existing is not None:
        user, _ = existing
        user_repository.update_password(conn, user.id, pwd)
        print(f"  Usuario '{username}' ya existía → contraseña reiniciada a {DEMO_PASSWORD}")
        return user.id
    user_id = user_repository.insert_user(
        conn,
        role_id=role_id,
        username=username,
        email=f"{username}@vetcare.demo",
        password_hash=pwd,
        full_name=full_name,
        phone="6000-0000",
    )
    print(f"  Usuario '{username}' creado ({role_name})")
    return user_id


def _already_seeded(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM owners WHERE identification = :ident",
            {"ident": "DEMO-OWNER-1"},
        )
        return cur.fetchone()[0] > 0


def seed() -> int:
    print("Sembrando datos de demostración VetCare…")
    with connection_scope(commit=True) as conn:
        admin_id = _ensure_user(
            conn, username="demo", full_name="Usuario Demo", role_name="ADMIN"
        )
        vet_id = _ensure_user(
            conn,
            username="vetdemo",
            full_name="Dra. Laura Demo",
            role_name="VETERINARIAN",
        )
        _ensure_user(
            conn,
            username="salesdemo",
            full_name="Mostrador Demo",
            role_name="SALES",
        )

        if _already_seeded(conn):
            print("  Datos DEMO- ya presentes; no se duplican propietarios/productos.")
            print("Listo.")
            return 0

        species = species_repository.list_species(conn)
        if not species:
            raise RuntimeError("No hay especies en el catálogo Oracle.")
        species_id = species[0][0]
        # Prefer Canine/Feline if names match.
        for sid, name in species:
            if "can" in name.lower() or "dog" in name.lower() or "perro" in name.lower():
                species_id = sid
                break
        breed_id = None
        breeds = species_repository.list_breeds(conn, species_id)
        if breeds:
            breed_id = breeds[0][0]

        owner1 = owner_repository.insert_owner(
            conn,
            identification="DEMO-OWNER-1",
            first_name="María",
            last_name="González",
            phone="8888-1001",
            secondary_phone=None,
            email="maria.demo@example.com",
            address="Barrio Demo 123",
            notes="Cliente frecuente (datos de prueba)",
        )
        owner2 = owner_repository.insert_owner(
            conn,
            identification="DEMO-OWNER-2",
            first_name="Carlos",
            last_name="Ramírez",
            phone="8888-1002",
            secondary_phone=None,
            email="carlos.demo@example.com",
            address="Calle Prueba 45",
            notes=None,
        )

        pet1 = pet_repository.insert_pet(
            conn,
            owner_id=owner1,
            species_id=species_id,
            breed_id=breed_id,
            name="Max",
            sex="MALE",
            birth_date=date(2021, 5, 12),
            approximate_age_months=None,
            color="Dorado",
            distinctive_features="Collar azul",
            microchip_number="DEMOCHIP001",
            photo_url=None,
            blood_type=None,
            allergies="Ninguna conocida",
            chronic_conditions=None,
        )
        pet2 = pet_repository.insert_pet(
            conn,
            owner_id=owner1,
            species_id=species_id,
            breed_id=breed_id,
            name="Luna",
            sex="FEMALE",
            birth_date=date(2022, 8, 3),
            approximate_age_months=None,
            color="Blanco y negro",
            distinctive_features=None,
            microchip_number="DEMOCHIP002",
            photo_url=None,
            blood_type=None,
            allergies=None,
            chronic_conditions=None,
        )
        pet3 = pet_repository.insert_pet(
            conn,
            owner_id=owner2,
            species_id=species_id,
            breed_id=breed_id,
            name="Rocky",
            sex="MALE",
            birth_date=None,
            approximate_age_months=36,
            color="Marrón",
            distinctive_features="Cicatriz en oreja",
            microchip_number=None,
            photo_url=None,
            blood_type=None,
            allergies="Polen",
            chronic_conditions=None,
        )

        now = datetime.now()
        appointment_repository.insert_appointment(
            conn,
            pet_id=pet1,
            veterinarian_id=vet_id,
            created_by=admin_id,
            appointment_at=now.replace(hour=10, minute=0, second=0, microsecond=0)
            + timedelta(days=0),
            reason="Control general",
            notes="Datos de prueba",
        )
        appointment_repository.insert_appointment(
            conn,
            pet_id=pet2,
            veterinarian_id=vet_id,
            created_by=admin_id,
            appointment_at=now.replace(hour=15, minute=30, second=0, microsecond=0)
            + timedelta(days=1),
            reason="Vacunación",
            notes=None,
        )

        cats = inventory_repository.list_categories(conn, active_only=True)
        cat_id = cats[0].id if cats else None

        supplier_id = inventory_repository.insert_supplier(
            conn,
            name="Distribuidora Demo Vet",
            tax_id="3-101-DEMO",
            contact_name="Ana Proveedora",
            phone="2222-3344",
            email="prov@demo.vet",
            address="Zona industrial demo",
        )

        products = [
            ("Croqueta Premium 3kg", "DEMO-SKU-001", "7790000111001", "bolsa", "28.50", "5", True, True),
            ("Antiparasitario spot-on", "DEMO-SKU-002", "7790000111002", "pipeta", "15.00", "8", True, True),
            ("Juguete cuerda", "DEMO-SKU-003", "7790000111003", "unidad", "6.75", "3", False, False),
            ("Shampoo hipoalergénico", "DEMO-SKU-004", "7790000111004", "botella", "12.00", "4", True, True),
        ]
        product_ids: list[int] = []
        for name, sku, barcode, unit, price, min_stock, req_lot, req_exp in products:
            pid = insert_product(
                conn,
                category_id=cat_id,
                name=name,
                sku=sku,
                barcode=barcode,
                description="Producto de demostración",
                unit=unit,
                sale_price=Decimal(price),
                minimum_stock=Decimal(min_stock),
                location="Estante Demo",
                requires_lot=req_lot,
                requires_expiry=req_exp,
            )
            product_ids.append(pid)
            qty = Decimal("25")
            lot_id = insert_lot(
                conn,
                product_id=pid,
                supplier_id=supplier_id,
                lot_number=f"DEMO-L-{sku[-3:]}",
                expiry_date=(date.today() + timedelta(days=180)) if req_exp else None,
                unit_cost=Decimal("5.00"),
                quantity_received=qty,
                notes="Lote demo",
            )
            insert_movement(
                conn,
                product_id=pid,
                lot_id=lot_id,
                movement_type="ENTRY",
                quantity=qty,
                reference_type="INVENTORY_LOT",
                reference_id=lot_id,
                performed_by=admin_id,
                notes="Carga inicial demo",
            )

        # Una venta pequeña de demostración
        sale_product = product_ids[2]  # juguete
        lots = inventory_repository.list_lots_for_product(
            conn, sale_product, available_only=True
        )
        lot = lots[0]
        invoice = sales_repository.next_invoice_number(conn, now)
        sale_id = sales_repository.insert_sale(
            conn,
            invoice_number=invoice,
            owner_id=owner1,
            sold_by=admin_id,
            subtotal=Decimal("6.75"),
            discount_amount=Decimal("0"),
            tax_amount=Decimal("0"),
            total=Decimal("6.75"),
            payment_method="CASH",
            status="COMPLETED",
            notes="Venta demo",
        )
        sales_repository.insert_sale_item(
            conn,
            sale_id=sale_id,
            product_id=sale_product,
            lot_id=lot.id,
            quantity=Decimal("1"),
            unit_price=Decimal("6.75"),
            discount_amount=Decimal("0"),
        )
        inventory_repository.adjust_lot_quantity(
            conn, lot.id, lot.quantity_available - Decimal("1")
        )
        insert_movement(
            conn,
            product_id=sale_product,
            lot_id=lot.id,
            movement_type="SALE",
            quantity=Decimal("1"),
            reference_type="SALE",
            reference_id=sale_id,
            performed_by=admin_id,
            notes=f"Venta {invoice}",
        )

        print(f"  Propietarios: María González, Carlos Ramírez")
        print(f"  Mascotas: Max, Luna, Rocky")
        print(f"  Citas: 2 (hoy y mañana)")
        print(f"  Productos: {len(product_ids)} con stock")
        print(f"  Venta demo: {invoice}")
        print("Listo (COMMIT).")
    return 0


def main() -> int:
    try:
        return seed()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR al sembrar datos: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
