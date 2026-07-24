from django.db import migrations, models
import django.db.models.deletion


def mover_productos_al_pedido(apps, schema_editor):
    InventarioLote = apps.get_model("negocio", "InventarioLote")
    lotes = list(InventarioLote.objects.select_related("paquete"))
    for lote in lotes:
        lote.pedido_id = lote.paquete.pedido_id
        lote.cantidad_recibida = (
            lote.cantidad_inicial if lote.paquete.entregado else 0
        )
    if lotes:
        InventarioLote.objects.bulk_update(
            lotes, ["pedido", "cantidad_recibida"]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("negocio", "0005_venta_cerrada_venta_fecha_cierre"),
    ]

    operations = [
        migrations.AddField(
            model_name="inventariolote",
            name="pedido",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lotes",
                to="negocio.pedido",
            ),
        ),
        migrations.AddField(
            model_name="inventariolote",
            name="cantidad_recibida",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(mover_productos_al_pedido, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="inventariolote",
            name="pedido",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lotes",
                to="negocio.pedido",
            ),
        ),
        migrations.RemoveField(
            model_name="inventariolote",
            name="paquete",
        ),
        migrations.RemoveField(
            model_name="paquete",
            name="entregado",
        ),
        migrations.RemoveField(
            model_name="paquete",
            name="fecha_entrega",
        ),
        migrations.AddConstraint(
            model_name="inventariolote",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    cantidad_recibida__lte=models.F("cantidad_inicial")
                ),
                name="inventario_recibido_no_supera_pedido",
            ),
        ),
    ]
