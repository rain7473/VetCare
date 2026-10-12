# Guía técnica de VetCare

## Principios de diseño

El flujo obligatorio es:

```text
PySide6 View → Service → Repository → Oracle
```

Las vistas recogen datos y presentan resultados. Los services validan permisos,
reglas y transacciones. Los repositories son la única capa con SQL. Los models
son dataclasses de dominio o proyecciones de solo lectura.

No se usa ORM; todas las consultas son explícitas y los valores se enlazan con
bind variables de python-oracledb. La conexión se abre mediante
`database.connection.connection_scope()` y siempre se cierra.

## Arranque y sesión

`main.select_first_window()` consulta `COUNT(*) FROM USERS`:

```text
0 usuarios → SetupWindow → crear ADMIN → LoginWindow
1+ usuarios → LoginWindow
```

Tras autenticar, `permission_service.load_role_permissions()` carga los códigos
del rol y `services.session` conserva usuario y permisos durante la sesión. La
sidebar se filtra con `MODULE_PERMISSIONS`; cada service vuelve a exigir su
permiso para impedir acceso por rutas internas.

Auditoría usa `SETTINGS_MANAGE` porque el esquema actual no contiene
`AUDIT_READ`. Crear un permiso específico exigiría una modificación autorizada
del esquema y de sus datos de roles.

## Transacciones críticas

### Ventas

`sales_service.complete_sale()` ejecuta en un único `connection_scope(commit=True)`:

1. valida carrito, propietario, precios y descuentos;
2. asigna stock por lotes FIFO;
3. inserta `SALES` y `SALE_ITEMS`;
4. actualiza `INVENTORY_LOTS.QUANTITY_AVAILABLE`;
5. inserta `STOCK_MOVEMENTS` tipo `SALE`;
6. agrega el evento de auditoría;
7. hace COMMIT solo si todo terminó correctamente.

`SALE_ITEMS.LINE_TOTAL` es virtual. Pasarlo al repository no causa INSERT; el
valor lo calcula Oracle.

### Historial clínico

Una consulta solo se edita en `DRAFT`. Al finalizar pasa a `FINALIZED`. El
sellado llama a `SEAL_CONSULTATION`; la verificación llama a
`VERIFY_CONSULTATION_HASH`. Las correcciones posteriores son filas nuevas en
`CLINICAL_AMENDMENTS`, nunca UPDATE de la consulta sellada.

### Inventario

El stock no se guarda en `PRODUCTS`: se calcula con
`SUM(INVENTORY_LOTS.QUANTITY_AVAILABLE)`. Toda entrada/ajuste crea su movimiento
en la misma transacción. Los tipos aceptados por el esquema son `ENTRY`, `SALE`,
`ADJUSTMENT_IN`, `ADJUSTMENT_OUT`, `EXPIRED`, `RETURN_IN` y `RETURN_OUT`.

## Dashboard

`dashboard_service` contiene la política por rol en un solo punto y
`dashboard_repository` concentra sus SELECT. ADMIN ve ocho métricas; RECEPTION
cuatro; VETERINARIAN cinco filtradas por `user.id` cuando el esquema permite
asignación; SALES cuatro. Las consultas usan fechas enlazadas y ventanas de 7 o
30 días.

La vista difiere la carga con `QTimer.singleShot(0, ...)`. Esto permite construir
el shell en pruebas offscreen sin exigir Oracle antes de iniciar el event loop.

## Selectores dinámicos y creación encadenada

`widgets.dynamic_selector.DynamicEntitySelector` es el único componente para
seleccionar entidades relacionadas. Usa un `QComboBox` editable y un
`QCompleter` filtrado por texto visible y atributos secundarios, pero expone
solo el ID de una fila realmente seleccionada. El texto manual invalida el ID.

El botón `+` vive fuera del popup y permanece visible con o sin coincidencias.
Las vistas conectan `add_requested` al diálogo existente, recargan únicamente
los datos del selector y llaman `select_id()` con el ID creado. Como el diálogo
padre sigue abierto, todos sus demás campos conservan su contenido.

`views.entity_creation` concentra los flujos compartidos. Actualmente soporta
Mascota → Propietario y creación de Veterinario; otras cadenas se componen en
sus propios diálogos (Espacio → Área, Producto → Categoría, entrada →
Proveedor/lote). El botón se deshabilita —sin ocultarse— cuando falta permiso o
el catálogo es controlado, como roles, especies o guías farmacológicas.

## Auditoría

`AUDIT_LOG` es append-only por `TRG_AUDIT_APPEND_ONLY`. La aplicación registra
login exitoso, administración de usuarios, ventas y movimientos de inventario;
el sellado clínico es auditado por la función Oracle existente. Los datos JSON
excluyen contraseñas y hashes.

El módulo de auditoría no expone INSERT, UPDATE ni DELETE. Sus filtros aceptan
solo campos conocidos y parámetros enlazados; el límite permitido es 1–500.

## Pruebas

## Inicio gráfico en Windows

Para uso normal, ejecute `launch_vetcare.vbs` o cree un acceso directo hacia
ese archivo. El lanzador resuelve el directorio del proyecto, utiliza
`.venv\Scripts\pythonw.exe` y abre `VetCare.pyw` con la consola oculta.

`python main.py` continúa disponible para depuración desde terminal. Los logs de
la aplicación gráfica rotan en `%LOCALAPPDATA%\VetCare\logs\vetcare.log`
(1 MB por archivo, tres copias). Login, configuración inicial y shell se muestran
maximizados; la transición oculta la pantalla anterior antes de mostrar la nueva.
`QLocalServer`/`QLocalSocket` limitan la ejecución a una sola instancia y activan
la ventana existente ante ejecuciones repetidas.

## Pruebas

Ejecute:

```powershell
python -m tests.run_all
```

`tests.run_all` lanza cada módulo en un proceso separado. Esto aísla QApplication,
sesiones globales y conexiones. Define `QT_QPA_PLATFORM=offscreen`. Los tests de
escritura abren `connection_scope()` sin `commit=True`, verifican dentro de la
transacción y confirman después que el ROLLBACK dejó la base intacta.

`tests.architecture_test` comprueba el límite de SQL, correspondencia entre
sidebar y permisos, y protección de `.env`. `tests.general_test` verifica roles,
tablas críticas, objetos Oracle válidos y el trigger append-only.
`tests.dynamic_selector_test` verifica filtrado por atributos, ID interno,
texto libre inválido, estado sin coincidencias y visibilidad permanente del `+`.

## Inspección del esquema

Antes de depender de una tabla o columna:

```powershell
python -m database.schema_inspector TABLA_1 TABLA_2 --rows 0
```

La herramienta solo ejecuta SELECT. Cualquier DDL requiere inspección, análisis
de impacto y autorización explícita antes de ejecutarse.

## Añadir o modificar un módulo

1. Inspeccione las tablas y constraints reales.
2. Defina o actualice el model.
3. Agregue SQL parametrizado al repository.
4. Implemente validaciones y transacción en el service.
5. Añada permiso a `MODULE_PERMISSIONS` usando un código existente autorizado.
6. Construya la view sin SQL.
7. Cree pruebas de permiso, validación, operación y ROLLBACK.
8. Ejecute la suite completa y actualice documentación.

No cambie contratos de columnas virtuales, estados o triggers para acomodar la
interfaz. La aplicación debe respetar las garantías de Oracle.

## Manejo de errores y secretos

- `DatabaseConnectionError` contiene mensajes aptos para UI; el detalle técnico
  va al log.
- No use `except: pass` ni muestre trazas al usuario final.
- Las contraseñas funcionales se procesan con bcrypt.
- `.env` no se versiona y `.env.example` mantiene `DB_PASSWORD=` vacío.
- El QR del carné no contiene información clínica.

