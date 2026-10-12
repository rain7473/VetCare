# Guía de usuario de VetCare

## Inicio de sesión y primer uso

Ejecute `python main.py`. Si `USERS` está vacío, el asistente solicita el
administrador principal y almacena la contraseña con bcrypt. En instalaciones
ya configuradas aparece el login. “Recordar usuario” conserva solo el nombre de
usuario, nunca la contraseña.

La aplicación utiliza una ventana principal con sidebar, topbar y páginas
internas. Cerrar sesión vuelve al login y limpia la sesión y sus permisos.

## Buscar y crear registros relacionados

Los selectores de propietarios, mascotas, veterinarios, vacunas, productos,
proveedores, áreas y otros catálogos permiten escribir para filtrar en tiempo
real. La búsqueda considera datos útiles como identificación, teléfono,
microchip, SKU o código de barras según el tipo de registro. Debe seleccionar
una coincidencia; un texto escrito que no corresponda a una fila no se guarda.

El botón `+` permanece visible aunque existan coincidencias. Al pulsarlo se abre
el formulario relacionado sin borrar lo que ya escribió. Al guardar, el nuevo
registro se selecciona automáticamente. Los flujos pueden encadenarse, por
ejemplo: **Consulta → Nueva mascota → Nuevo propietario → guardar y regresar**.
Si cancela cualquier ventana, vuelve al formulario anterior sin cambios. El `+`
aparece deshabilitado cuando su rol no tiene permiso para crear ese registro.

## Dashboard

Use **Actualizar dashboard** para renovar los indicadores.

- ADMIN: mascotas, citas, hospitalizados, alertas, stock, vencimientos, ventas
  y usuarios.
- RECEPTION: citas de hoy, pacientes en atención, triajes y próximas citas.
- VETERINARIAN: consultas propias, hospitalizados/alertas asignados, pacientes
  asignados y próximas vacunas.
- SALES: productos, stock bajo, ventas del día y vencimientos.

Los paneles muestran agenda de siete días, próxima cita y actividad pertinente
al rol. La ventana de vencimientos y vacunas del dashboard es de 30 días.

## Flujo de recepción

1. Registre o localice al propietario.
2. Registre la mascota y sus datos identificativos.
3. Cree la cita y asigne veterinario cuando corresponda.
4. Confirme la cita y cambie su estado conforme avanza la atención.
5. Registre el triaje. La prioridad es apoyo operativo y no sustituye el juicio
   de un veterinario.

Los propietarios y mascotas se desactivan mediante estado; no se borran.

## Flujo clínico

1. Abra **Consultas** y cree una consulta en `DRAFT`.
2. Registre motivo, síntomas, observaciones, vitales y diagnósticos.
3. Use la calculadora farmacológica solo con guías configuradas; VetCare no
   inventa dosis.
4. Agregue prescripciones, cirugía o vacunación según el caso.
5. Finalice la consulta. Una consulta `FINALIZED` deja de ser editable.
6. Selle la consulta. Oracle genera el SHA-256 y el estado pasa a `SEALED`.
7. Use **Verificar integridad** para comprobar el sello.

Una consulta sellada nunca debe editarse. Registre una enmienda con autor,
motivo y texto; las enmiendas son append-only.

## Hospitalización y alertas

Hospitalice desde el módulo correspondiente, asigne área/espacio y registre
mediciones sucesivas. Las alertas solo se generan cuando existen rangos vitales
configurados para la especie. Pueden pasar de `OPEN` a `ACKNOWLEDGED` y luego a
`RESOLVED`. Al dar el alta se libera el espacio.

## Carné digital

Desde la ficha de mascota abra el carné digital. El QR contiene únicamente un
token público con formato `vetcare:pet:<hex>`; no contiene diagnósticos,
alergias ni otros datos clínicos. Reemitir el carné invalida el token anterior.

## Inventario y barcode

El stock visible es la suma disponible de todos los lotes. Registre entradas
con lote y vencimiento cuando el producto lo exija. Los ajustes requieren un
tipo válido y no permiten dejar cantidades negativas.

En campos de barcode, enfoque el control y escanee con el lector USB. El lector
se interpreta como teclado y confirma normalmente con Enter.

## Ventas

1. Busque o escanee el producto.
2. Agregue cantidad y revise precio/descuento.
3. Seleccione propietario opcional y método de pago.
4. Confirme la venta.

La confirmación crea venta e ítems, descuenta lotes FIFO y registra movimientos
`SALE` en una única transacción. Si una parte falla, no queda venta ni descuento
de stock parcial.

## Usuarios y auditoría

ADMIN puede crear, editar, activar/desactivar usuarios y restablecer
contraseñas. El sistema impide desactivar la propia cuenta o dejar la clínica
sin un ADMIN activo.

En **Auditoría**, filtre por entidad, acción, usuario o fechas. El detalle
muestra JSON anterior/nuevo cuando existe. La pantalla es de solo lectura y la
base bloquea UPDATE/DELETE sobre la bitácora.

## Problemas frecuentes

- **No conecta a Oracle:** confirme que XE y `XEPDB1` estén activos, revise
  host/puerto/service y ejecute `python -m tests.db_health_test`.
- **Permiso denegado:** el rol no tiene el código necesario en Oracle. No se
  resuelve ocultando o forzando la pantalla.
- **No aparece una alerta clínica:** confirme que haya un rango activo para la
  especie y parámetro medido.
- **Stock insuficiente:** revise lotes disponibles; el total del catálogo no se
  mantiene en una columna independiente.
- **Consulta no editable:** `FINALIZED` y `SEALED` son estados protegidos; use
  una enmienda cuando corresponda.

