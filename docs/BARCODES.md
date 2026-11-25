# Códigos de barras de VetCare

## Uso

1. En Inventario, cree o edite un producto. El campo Código de barras acepta
   escritura, pegado y lectores USB que actúan como teclado. Enter termina la
   captura y pasa a Unidad, sin guardar accidentalmente el formulario.
2. Si no tiene código, pulse Generar. Se propone un identificador UUID completo
   con prefijo VC, representado en Code 128. Se muestra la vista previa. El
   identificador se guarda en Oracle al pulsar Guardar; cancelar no lo registra.
   Generar queda deshabilitado cuando existe un código y nunca sustituye uno
   guardado del fabricante. La edición manual sigue disponible explícitamente.
3. Seleccione el producto y pulse Etiqueta para imprimir o exportar PNG/PDF.
   La etiqueta usa los datos guardados: nombre, código y precio. Para cambios
   de precio o nombre, guarde primero el producto. Detalles muestra también el
   código y stock. La búsqueda admite nombre, código, SKU, categoría y ubicación.
4. En Ventas, abra Agregar venta. Introduzca el código en Escanear o ingresar
   código y pulse Enter. Cada lectura agrega una unidad; el mismo producto
   permanece en una sola fila. Los códigos inexistentes y el stock insuficiente
   aparecen en el mensaje del lector sin interrumpirlo con un diálogo.
5. F2 vuelve al campo de lectura. F4 confirma la venta usando la lógica existente
   de descuentos, impuestos y asignación por lotes. Tras el éxito, el carrito
   queda vacío y el lector listo para otra venta. También puede buscar productos
   en el selector y pulsar Agregar.

Para pruebas sin hardware, copie un código de Inventario, péguelo en el lector
de Ventas y pulse Enter. Repita para aumentar cantidad. Use un código inexistente
para comprobar el aviso. No es necesario configurar un servicio externo.

## Formatos y etiquetas

Se conservan los caracteres y ceros iniciales del código. Se admiten hasta
100 caracteres ASCII imprimibles. EAN-13 y UPC-A con checksum válido se dibujan
en su simbología original; los demás valores, incluidos los códigos históricos
de la base cuyos dígitos no cumplen esos checksums, se dibujan en Code 128 sin
alterar su contenido. Los códigos internos siempre usan Code 128.

Algunos lectores transmiten un UPC-A como EAN-13 con cero inicial. La búsqueda
prueba primero el código exacto y después su equivalente válido, manteniendo
el valor almacenado. Si existen ambos valores en productos distintos, prevalece
la coincidencia exacta; configure el lector de forma consistente en ese caso.

Las barras se dibujan como rectángulos negros sobre blanco, con módulos de
0.254 mm y zonas libres laterales de al menos diez módulos. La etiqueta tiene
38.1 mm de alto y ancho variable según el contenido, indicado en la vista
previa. El PNG tiene resolución de 300 DPI y el PDF contiene barras vectoriales.
El diálogo de impresión permite seleccionar impresora y papel. Se rechaza un
papel más pequeño que la etiqueta; no se comprimen las barras. Imprima al 100 %,
sin ajustar a página. La calidad de la impresión física debe comprobarse con
su papel, impresora y lector; no se realizó una impresión física en estas pruebas.

## Datos y transacciones

La arquitectura se mantiene: VIEW → SERVICE → REPOSITORY → ORACLE.
`PRODUCTS.BARCODE` y su restricción UNIQUE ya existían y se reutilizan. Las
validaciones incluyen productos inactivos al comprobar duplicados. Una colisión
entre prevalidación e INSERT/UPDATE también se traduce a un mensaje de validación
desde la restricción Oracle. No se genera ni se migra ningún código existente.

La migración `database/migrations/20261114_barcode_sales.sql` agrega únicamente
`SALES.REQUEST_KEY`, `SALES.REQUEST_HASH` y una restricción única para la clave.
Es aditiva, idempotente y conserva todas las ventas anteriores con campos nulos.
La aplicación no ejecuta DDL al iniciar. En otros esquemas, instale dependencias
y ejecute `python -m scripts.apply_barcode_migration` antes de abrir la versión
actualizada, o ejecute el SQL como VETCARE desde SQL Developer/SQL*Plus.

Cada carrito conserva su clave mientras se reintenta la confirmación. Oracle
devuelve la venta ya registrada cuando coinciden la clave, el vendedor y los
datos, sin crear otra venta, auditoría o movimiento. Una clave reutilizada con
datos distintos se rechaza. El botón queda bloqueado durante la confirmación.
Al vaciar el carrito o terminar una venta se inicia una nueva clave.

Las confirmaciones se serializan mediante un bloqueo de SALES durante la
transacción, manteniendo la numeración diaria existente `VC-YYYYMMDD-NNNN`.
Las consultas siguen disponibles; otra confirmación espera hasta diez segundos
y puede reintentarse si falla. Los lotes se bloquean al asignar FIFO y también
al ajustar cantidades, para evitar lecturas y descuentos concurrentes perdidos.
Venta, ítems, stock, movimientos y auditoría se confirman juntos o se revierten.
Escanear y agregar manualmente nunca escriben stock.

## Archivos

- `utils/barcodes.py`: validación, UUID, simbologías y equivalencia UPC/EAN.
- `utils/barcode_label.py`: dibujo común, dimensiones, PNG, PDF e impresión.
- `views/inventory/barcode_label_dialog.py`: vista, exportación e impresión.
- `views/inventory/inventory_dialogs.py`: campo, generación y vista previa.
- `views/inventory/inventory_page.py`: búsqueda, detalles, columna y etiquetas.
- `widgets/barcode_scanner.py`: Enter consumido, limpieza y protección de reentrada.
- `views/sales/sales_page.py`: lector, avisos, carrito, foco, atajos y confirmación.
- `services/inventory_service.py`: validación y generación conectadas a Oracle.
- `services/sales_service.py`: idempotencia, reglas, transacción y auditoría única.
- `repositories/inventory_repository.py`: bloqueo de lotes.
- `repositories/sales_repository.py`: clave de solicitud y bloqueo de confirmaciones.
- `database/migrations/20261114_barcode_sales.sql` y
  `scripts/apply_barcode_migration.py`: migración explícita.
- `requirements.txt`: python-barcode; Qt y Pillow ya formaban parte del proyecto.
- `requirements-test.txt`, `tests/barcode_system_test.py` y `tests/run_all.py`:
  dependencias de pruebas, cobertura nueva y registro en la suite.
- `README.md` y esta guía: instalación, operación y verificación.

## Verificación

```powershell
python -m pip install -r requirements-test.txt
python -m tests.barcode_system_test
python -m tests.run_all
```

Las 19 pruebas nuevas cubren registro y edición, generación y guardado,
duplicados en servicio y restricción Oracle, productos inactivos, búsqueda,
captura USB simulada con Qt, Enter sin guardado/confirmación accidental,
escaneos consecutivos, carrito manual, cantidad fraccionaria insuficiente,
totales, confirmación con F4, reentrada, reintentos, descuento único y auditoría,
rollback tras fallo inducido y dos confirmaciones concurrentes con conexiones
reales. La concurrencia usa ventas revertidas; no modifica ventas existentes.

ZXing-C++ lee independientemente etiquetas PNG y PDFs rasterizados con PyMuPDF:
Code 128 interno, EAN-13, UPC-A, un código histórico y el máximo de 100 caracteres.
También se verifica que un papel pequeño sea rechazado. Estas herramientas
solo son necesarias para ejecutar las pruebas, no para operar VetCare.

Las ventas de prueba usan ROLLBACK. La prueba de reinicio guarda un producto
temporal con SKU único, lo consulta desde un intérprete Python nuevo y elimina
únicamente ese registro por ID y SKU en `finally`. No se confirma ninguna venta
de prueba ni se altera el stock de los productos existentes.
