from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


def distribuir_comisiones(apps, schema_editor):
    Distribucion = apps.get_model("negocio", "DistribucionGanancia")
    Detalle = apps.get_model("negocio", "DetalleVenta")

    for distribucion in Distribucion.objects.filter(detalle_venta__isnull=True):
        detalles = list(
            Detalle.objects.filter(venta_id=distribucion.venta_id).order_by("id")
        )
        if not detalles:
            continue

        importes = [
            Decimal(detalle.cantidad) * detalle.precio_unitario_venta
            for detalle in detalles
        ]
        venta_bruta = sum(importes, Decimal("0"))
        restante = distribucion.monto

        for indice, detalle in enumerate(detalles):
            if indice == len(detalles) - 1:
                monto = restante
            elif venta_bruta:
                monto = (
                    distribucion.monto * importes[indice] / venta_bruta
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                restante -= monto
            else:
                monto = Decimal("0")

            if indice == 0:
                distribucion.detalle_venta_id = detalle.id
                distribucion.monto = monto
                distribucion.save(update_fields=["detalle_venta", "monto"])
            else:
                Distribucion.objects.create(
                    venta_id=distribucion.venta_id,
                    detalle_venta_id=detalle.id,
                    persona_id=distribucion.persona_id,
                    monto=monto,
                    pagado=distribucion.pagado,
                    fecha_pago=distribucion.fecha_pago,
                )


class Migration(migrations.Migration):
    dependencies = [
        ("negocio", "0003_remove_distribucionganancia_distribucion_venta_persona_unica_and_more"),
    ]

    operations = [
        migrations.RunPython(distribuir_comisiones, migrations.RunPython.noop),
    ]
