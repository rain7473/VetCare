# VetCare

Sistema de Gestión Integral para Clínica Veterinaria. Aplicación de escritorio
en Python/PySide6 conectada a Oracle XE para operación clínica, administrativa
y comercial.

Los objetivos 1–25 están implementados y la suite general pasa 27 módulos de
prueba. El esquema Oracle se considera preexistente: la aplicación no crea ni
modifica tablas automáticamente.

## Funcionalidad

- Primer inicio y creación segura del ADMIN inicial.
- Login con bcrypt, sesiones y permisos centralizados desde Oracle.
- Propietarios, mascotas, fotografías y carné digital con QR público.
- Citas, triaje, consultas, diagnósticos, signos vitales y prescripciones.
- Cálculo farmacológico basado únicamente en parámetros configurados.
- Cirugía, vacunas, hospitalización, monitoreo y alertas clínicas.
- Historial clínico `DRAFT → FINALIZED → SEALED`, SHA-256 y enmiendas append-only.
- Inventario por lotes, movimientos, stock bajo, vencimientos y barcode USB.
- Ventas atómicas con descuento FIFO de lotes.
- Dashboard con métricas y actividad adaptadas a cada rol.
- Auditoría administrativa append-only con filtros y detalle JSON.
- Selectores dinámicos reutilizables con búsqueda por múltiples atributos,
  botón `+` siempre visible y creación encadenada de registros relacionados.

## Requisitos

- Python 3.12 o superior.
- Oracle Database XE con PDB `XEPDB1` y esquema `VETCARE` ya creado.
- Acceso local al listener Oracle en el puerto configurado.
- Windows/PowerShell para los comandos de esta guía; el código Python no depende
  de rutas absolutas del equipo.

Dependencias Python principales: PySide6, QtAwesome, python-oracledb, python-dotenv,
bcrypt, qrcode y Pillow.

## Instalación rápida

```powershell
cd C:\ruta\a\VetCare
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Complete únicamente la contraseña local en `.env`:

```env
DB_USER=VETCARE
DB_PASSWORD=contraseña_local
DB_HOST=localhost
DB_PORT=1521
DB_SERVICE=XEPDB1
```

`.env` está ignorado por Git y nunca debe versionarse. `VETCARE` es el usuario
técnico de Oracle; las personas de la clínica se autentican contra `USERS`.

Verifique la conexión y ejecute la aplicación:

```powershell
python -m tests.db_health_test
python main.py
```

El comando anterior es para desarrollo y mantiene visible el terminal desde el
que se ejecutó. Para generar el ejecutable con nombre e icono de VetCare:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\scripts\build_executable.ps1
```

El resultado es `VetCare.exe` en la raíz del proyecto. Mantenga `.env` y la
carpeta `data` junto a ese ejecutable para conservar la conexión y las fotos.
En Windows, el inicio normal se hace con doble clic en `launch_vetcare.vbs`:
abre `VetCare.exe` sin consola; si aún no existe, usa `pythonw.exe` como modo de
desarrollo. `VetCare.pyw` es el punto de entrada gráfico equivalente. VetCare
permite una sola instancia: un segundo doble clic activa la ventana existente.

Los mensajes técnicos se guardan en
`%LOCALAPPDATA%\VetCare\logs\vetcare.log`; no se muestran al usuario final.
En Visual Studio Code use **Ejecutar y depurar → VetCare (sin terminal)**; la
configuración local evita abrir el terminal integrado.

En una instalación sin filas en `USERS`, VetCare muestra la configuración del
primer ADMIN. Si ya existe cualquier usuario —incluso inactivo— abre el login y
bloquea el bootstrap.

## Datos de demostración

El siguiente comando hace **COMMIT real**. Es idempotente para los registros
marcados como demo, no elimina usuarios existentes y reinicia la contraseña de
los usuarios demo si ya existen.

```powershell
python -m scripts.seed_demo_data
```

Contraseña común: `Demo1234`.

| Usuario | Rol | Uso sugerido |
|---|---|---|
| `demo` | ADMIN | Recorrido completo y auditoría |
| `vetdemo` | VETERINARIAN | Flujo clínico y hospitalización |
| `salesdemo` | SALES | Inventario de lectura y ventas |

La siembra incluye a María González, Carlos Ramírez, Max, Luna y Rocky; cuatro
productos con barcode `7790000111001`–`7790000111004`, stock y una venta demo.

## Roles y acceso

Los permisos se cargan desde `PERMISSIONS`/`ROLE_PERMISSIONS` y se validan tanto
en la navegación como en services. No se confía solo en ocultar botones.

| Rol | Ámbito principal |
|---|---|
| ADMIN | Administración completa, usuarios, configuración y auditoría |
| RECEPTION | Propietarios, mascotas, citas, triaje y ventas autorizadas |
| VETERINARIAN | Historial, consultas, cirugía, vacunas y hospitalización |
| SALES | Productos, stock y ventas; sin historial clínico completo |

El módulo Auditoría usa `SETTINGS_MANAGE`, permiso ya existente y exclusivo de
ADMIN. No se alteró el esquema para agregar un permiso nuevo.

## Arquitectura

```text
VIEW → SERVICE → REPOSITORY → ORACLE
```

- `views/`: interfaz, eventos y presentación; no contiene SQL.
- `services/`: permisos, validaciones, reglas y límites transaccionales.
- `repositories/`: SQL parametrizado y llamadas PL/SQL.
- `models/`: entidades y modelos de solo lectura.
- `database/`: conexión centralizada e inspección segura del esquema.
- `widgets/`: componentes PySide6 reutilizables.
- `tests/`: pruebas aisladas, Oracle con ROLLBACK y Qt offscreen.

Las ventas, entradas/ajustes de stock y eventos de auditoría relacionados se
escriben en una sola transacción. `SALE_ITEMS.LINE_TOTAL` es virtual y nunca se
inserta. El stock es la suma de `INVENTORY_LOTS.QUANTITY_AVAILABLE`.

Más detalle en la [guía técnica](docs/TECHNICAL_GUIDE.md).

## Pruebas

La suite completa es el comando recomendado:

```powershell
python -m tests.run_all
```

Ejecuta 25 módulos en procesos aislados, fuerza Qt offscreen y cubre conexión,
arquitectura, seguridad, permisos, módulos clínicos, inventario, ventas,
dashboard, auditoría e interfaz. Los tests que escriben usan INSERT + ROLLBACK.

Comandos útiles:

```powershell
python -m tests.run_all --fail-fast
python -m tests.smoke_test
python -m tests.dashboard_test
python -m tests.audit_test
python -m tests.dynamic_selector_test
python -m tests.pet_profile_test
python -m tests.icons_test
python -m database.schema_inspector NOMBRE_TABLA --rows 5
```

El inspector es de solo lectura. No ejecute DDL contra el esquema desde la app.

### Iconografía y perfil de mascotas

`utils/icons.py` centraliza Font Awesome Solid mediante QtAwesome: nombres
semánticos, tamaños de 14/18/28 px y colores VetCare para los estados del icono.
Las vistas usan `icon()`, `icon_label()` o `set_button_icon()` después de crear
`QApplication`. La navegación, los indicadores y las acciones de los módulos
comparten este catálogo.

El perfil de Mascotas conserva dos columnas desde 440 px de ancho del panel,
desplazamiento interno y acciones inferiores fijas. Las pestañas tienen paleta
clara explícita para evitar fondos oscuros del tema de Windows. Se puede generar
una vista previa a 1366×768 y 1920×1080, leyendo las mascotas de Oracle, con
`python -m scripts.preview_pet_profile --output-dir RUTA`. Este comando usa Qt
offscreen y no abre ventanas en el escritorio.

## Dashboard analítico con PyQtGraph

El Dashboard utiliza PyQtGraph 0.14 con el backend **PySide6**, QtAwesome y
una dona dibujada con Qt. La dependencia está en `requirements.txt`; para
actualizar el entorno existente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Incluye tarjetas navegables, consultas e ingresos mensuales, distribución por
especie, estados reales de citas, próximas citas, alertas priorizadas y los
cinco eventos de auditoría más recientes del período. Los accesos rápidos
reutilizan los formularios de Mascotas, Citas, Consultas y Triaje.

- **Período:** Hoy, últimos 7/30 días, este mes o rango personalizado inclusivo.
  Los KPI de consultas e ingresos, los estados de citas y la actividad se
  filtran por ese intervalo. Las fechas del dashboard se interpretan en Panamá.
- **Contexto mensual:** gris = histórico de seis meses hasta el fin elegido;
  turquesa = registros dentro del filtro. Un rango personalizado mayor conserva
  todos sus meses. Al pasar el cursor se muestran los importes/conteos exactos.
  En ingresos, la casilla de comparación añade los mismos meses del año anterior
  en mint. Solo cuentan ventas `COMPLETED`; no equivale a beneficio contable.
- **Tendencias:** comparan el período seleccionado con el intervalo anterior de
  igual duración. Sin base previa no se presenta un porcentaje inventado.
- **Estado actual:** mascotas, hospitalizados, alertas, stock, usuarios y la dona
  no cambian con el filtro. Los KPI que dicen «hoy» conservan su alcance diario.
  Las próximas citas parten de ahora y cubren los siguientes siete días.
- **Vacunas pendientes:** mascotas activas; última aplicación de cada vacuna,
  con próxima fecha vencida o hasta los siguientes 30 días. No se infieren
  esquemas de vacunación ni vacunas nunca registradas.
- **Permisos:** el servicio valida la sesión y cruza rol con permisos cargados
  de Oracle. Veterinarios ven consultas/citas/hospitalizaciones asignadas;
  ventas ve importes propios, sin datos clínicos. Sin acceso a Auditoría, la
  actividad se limita a eventos propios y no ofrece enlace a esa pantalla.
- **Rendimiento:** un worker por página, conexiones cerradas al finalizar,
  transacción de solo lectura consistente y consultas agregadas. Cambiar filtros
  durante una carga conserva únicamente la última selección. Al fallar, se
  mantienen los últimos datos con su fecha de actualización y se permite reintentar.

Verificación reproducible:

```powershell
.\.venv\Scripts\python.exe -m tests.dashboard_test
.\.venv\Scripts\python.exe -m tests.run_all
.\.venv\Scripts\python.exe -m scripts.preview_dashboard --output-dir RUTA
```

La vista previa usa datos reales y renderiza la ventana principal a 1366×768 y
1920×1080 sin abrir ventanas en el escritorio ni escribir en Oracle. Las pruebas
de agregados crean registros temporales dentro de una transacción con rollback.

Archivos del rediseño: `models/dashboard.py`, `repositories/dashboard_repository.py`,
`services/dashboard_service.py`, `views/dashboard/dashboard_page.py`,
`views/main_window.py`, `widgets/stat_card.py`, `widgets/dashboard_charts.py`,
`assets/styles/main.qss`, `requirements.txt`, `tests/dashboard_test.py`,
`scripts/preview_dashboard.py` y este README.

## Reglas Oracle relevantes

- `SYSTEM_SETTINGS.SETTING_VALUE` contiene JSON con forma `{"value": ...}`.
- Consultas: `DRAFT → FINALIZED → SEALED`; el sellado y verificación usan las
  funciones Oracle `SEAL_CONSULTATION` y `VERIFY_CONSULTATION_HASH`.
- Un registro sellado no se edita; las correcciones van a
  `CLINICAL_AMENDMENTS`.
- `AUDIT_LOG` y las enmiendas están protegidos contra UPDATE/DELETE.
- El QR contiene `vetcare:pet:<hex>` y no incluye datos clínicos sensibles.
- Movimientos válidos: `ENTRY`, `SALE`, `ADJUSTMENT_IN`, `ADJUSTMENT_OUT`,
  `EXPIRED`, `RETURN_IN`, `RETURN_OUT`.

## Documentación

- [Guía de usuario](docs/USER_GUIDE.md)
- [Guía técnica y de mantenimiento](docs/TECHNICAL_GUIDE.md)

## Limitaciones conocidas

- Configuración permite guardar nombre, teléfono, correo y dirección en
  SYSTEM_SETTINGS, con auditoría y permiso SETTINGS_MANAGE. Incluye acceso a
  rangos vitales y preferencias locales de avisos para el usuario actual.
- La búsqueda de la barra superior aparece únicamente en el Dashboard y ofrece
  coincidencias debajo del campo mientras se escribe, desde el primer carácter
  (hasta diez por módulo). Consulta propietarios, mascotas, citas y consultas
  según permisos. Clic o flechas y Enter abren el identificador exacto. Los demás
  módulos conservan sus buscadores y filtros propios.
- La campana revisa automáticamente el resumen de alertas del dashboard cada
  60 segundos (configurable entre 30 y 3600). Incluye próximas citas, vacunas
  pendientes, alertas clínicas, stock y vencimientos según permisos. Es un
  resumen limitado; sus enlaces abren los módulos para consultar todos los
  registros. Los avisos de escritorio agrupan novedades durante la sesión.
  Requieren VetCare abierto y notificaciones habilitadas en Windows; no existe
  un servicio externo para recibir push con la aplicación cerrada.
- El barcode inicial asume un lector USB que actúa como teclado.
- El perfil de Mascotas muestra consultas, vacunas y el último peso clínico
  registrado según permisos. El esquema actual no incluye tamaño, notas
  propias de la mascota ni adjuntos: se muestran las observaciones clínicas
  y la foto existente, sin crear campos ni datos ficticios.

## Estado de objetivos

| Objetivos | Resultado |
|---|---|
| 1–6 | Base, Oracle, bootstrap, login, shell y permisos ✅ |
| 7–16 | Operación clínica y hospitalaria ✅ |
| 17–21 | Integridad, carné, inventario, barcode y ventas ✅ |
| 22 | Dashboard por rol ✅ |
| 23 | Auditoría append-only ✅ |
| 24 | Suite general automatizada ✅ |
| 25 | Documentación técnica y de usuario ✅ |
