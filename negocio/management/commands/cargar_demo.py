from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from negocio.models import (
    Cliente,
    DetalleVenta,
    InventarioLote,
    Marca,
    Paquete,
    Pedido,
    Producto,
    TipoPago,
    TipoProducto,
    Venta,
)


class Command(BaseCommand):
    help = "Carga datos de ejemplo sin duplicarlos."

    def handle(self, *args, **options):
        skincare, _ = TipoProducto.objects.get_or_create(nombre="Skincare")
        maquillaje, _ = TipoProducto.objects.get_or_create(nombre="Maquillaje")
        cabello, _ = TipoProducto.objects.get_or_create(nombre="Cabello")

        ordinary, _ = Marca.objects.get_or_create(nombre="The Ordinary")
        cerave, _ = Marca.objects.get_or_create(nombre="CeraVe")
        elf, _ = Marca.objects.get_or_create(nombre="e.l.f.")
        olaplex, _ = Marca.objects.get_or_create(nombre="Olaplex")

        productos = [
            Producto.objects.get_or_create(
                nombre="Niacinamide 10% + Zinc 1%",
                defaults={
                    "marca": ordinary,
                    "tipo_producto": skincare,
                    "link": "https://theordinary.com/",
                },
            )[0],
            Producto.objects.get_or_create(
                nombre="Limpiador facial hidratante",
                defaults={
                    "marca": cerave,
                    "tipo_producto": skincare,
                    "link": "https://www.cerave.com/",
                },
            )[0],
            Producto.objects.get_or_create(
                nombre="Halo Glow Liquid Filter",
                defaults={
                    "marca": elf,
                    "tipo_producto": maquillaje,
                    "link": "https://www.elfcosmetics.com/",
                },
            )[0],
            Producto.objects.get_or_create(
                nombre="No. 3 Hair Perfector",
                defaults={
                    "marca": olaplex,
                    "tipo_producto": cabello,
                    "link": "https://olaplex.com/",
                },
            )[0],
        ]

        ahora = timezone.now()
        pedido_1, creado = Pedido.objects.get_or_create(
            cuenta="Cuenta Miami",
            propietario="Diego Ramírez",
            defaults={
                "fecha": ahora - timedelta(days=18),
                "direccion": "Casillero 4821, Miami, Florida",
                "descuento": Decimal("18.00"),
                "dolar_valor": Decimal("3.7450"),
            },
        )
        if creado:
            paquete = Paquete.objects.create(
                pedido=pedido_1, codigo_seguimiento="USPS-9400-1000-001", entregado=False
            )
            for producto, cantidad, usd, soles in [
                (productos[0], 12, "8.90", "33.33"),
                (productos[2], 8, "14.00", "52.43"),
            ]:
                InventarioLote.objects.create(
                    paquete=paquete,
                    producto=producto,
                    cantidad_inicial=cantidad,
                    costo_unitario_dolar=Decimal(usd),
                    costo_unitario_soles=Decimal(soles),
                    costo_soles_manual=False,
                )

        pedido_2, creado = Pedido.objects.get_or_create(
            cuenta="Cuenta Amazon",
            propietario="María Torres",
            defaults={
                "fecha": ahora - timedelta(days=43),
                "direccion": "Av. Arequipa 1550, Lima",
                "descuento": Decimal("0.00"),
                "dolar_valor": Decimal("3.7200"),
            },
        )
        if creado:
            paquete = Paquete.objects.create(
                pedido=pedido_2,
                codigo_seguimiento="AMZ-7842-PE",
                entregado=True,
                fecha_entrega=ahora - timedelta(days=31),
            )
            for producto, cantidad, usd, soles in [
                (productos[1], 10, "12.50", "46.50"),
                (productos[3], 6, "30.00", "111.60"),
            ]:
                InventarioLote.objects.create(
                    paquete=paquete,
                    producto=producto,
                    cantidad_inicial=cantidad,
                    costo_unitario_dolar=Decimal(usd),
                    costo_unitario_soles=Decimal(soles),
                    costo_soles_manual=False,
                )

        yape, _ = TipoPago.objects.get_or_create(nombre="Yape")
        transferencia, _ = TipoPago.objects.get_or_create(nombre="Transferencia")
        efectivo, _ = TipoPago.objects.get_or_create(nombre="Efectivo")
        ana, _ = Cliente.objects.get_or_create(
            nombre="Ana Castillo", defaults={"telefono": "999 123 456"}
        )
        lucia, _ = Cliente.objects.get_or_create(
            nombre="Lucía Mendoza", defaults={"telefono": "988 456 321"}
        )

        ventas_demo = [
            (ana, yape, 3, "Entregado", True, [(productos[0], 2, "69.90"), (productos[2], 1, "89.90")]),
            (lucia, transferencia, 12, "En camino", True, [(productos[1], 1, "82.00")]),
            (ana, efectivo, 36, "Entregado", False, [(productos[3], 1, "179.00")]),
        ]
        for cliente, pago, dias, estado, pagado, detalles in ventas_demo:
            fecha = ahora - timedelta(days=dias)
            venta, creada = Venta.objects.get_or_create(
                cliente=cliente,
                tipo_pago=pago,
                direccion_entrega="DEMO · Lima, Perú",
                defaults={
                    "fecha": fecha,
                    "descuento": Decimal("10.00") if dias == 3 else Decimal("0.00"),
                    "pagado": pagado,
                    "estado_entrega": estado,
                },
            )
            if creada:
                for producto, cantidad, precio in detalles:
                    DetalleVenta.objects.create(
                        venta=venta,
                        producto=producto,
                        cantidad=cantidad,
                        precio_unitario_venta=Decimal(precio),
                    )

        self.stdout.write(self.style.SUCCESS("Datos de demostración listos."))
