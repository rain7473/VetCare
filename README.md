# VetCare

Sistema de Gestión Integral para Clínica Veterinaria.

Aplicación de escritorio profesional para la administración clínica,
administrativa y comercial de una clínica veterinaria.

## Stack tecnológico

- Python 3.12+
- PySide6 (interfaz gráfica)
- Oracle Database XE (PDB `XEPDB1`, esquema `VETCARE`)
- python-oracledb (driver Oracle)
- python-dotenv (variables de entorno)
- bcrypt (hash de contraseñas)
- qrcode + Pillow (carné digital / QR)

## Arquitectura

Flujo de responsabilidades:

```text
VIEW → SERVICE → REPOSITORY → ORACLE
```

```text
VetCare/
├── main.py            # Punto de entrada
├── config/            # Settings (.env) y constantes (identidad visual)
├── database/          # Conexión Oracle centralizada (Objetivo 2)
├── models/            # Entidades lógicas
├── repositories/      # Única capa con SQL (parametrizado)
├── services/          # Reglas de negocio y validaciones
├── views/             # Interfaz PySide6 (sin SQL)
├── widgets/           # Componentes reutilizables (sidebar, cards...)
├── utils/             # Validadores, seguridad, imágenes, QR
├── assets/            # Íconos, imágenes, logos y estilos QSS
└── tests/             # Pruebas
```

## Instalación

Requisitos previos: Python 3.12+ y Oracle XE con el esquema `VETCARE` ya creado.

```powershell
# 1. Crear entorno virtual
py -m venv .venv

# 2. Activarlo (PowerShell)
.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt
```

## Configuración

Copiar `.env.example` a `.env` y completar la contraseña local:

```env
DB_USER=VETCARE
DB_PASSWORD=tu_contraseña_local
DB_HOST=localhost
DB_PORT=1521
DB_SERVICE=XEPDB1
```

`.env` está en `.gitignore`: **nunca** se sube al repositorio.

> Nota: `VETCARE` es el usuario técnico de Oracle (conexión de la app).
> Los usuarios reales de la clínica viven en la tabla `USERS` y se
> autentican dentro de la aplicación, no contra cuentas Oracle.

## Ejecución

```powershell
python main.py
```

## Pruebas

```powershell
# Prueba de humo de la interfaz (no requiere Oracle)
python -m tests.smoke_test

# Prueba de conexión a Oracle (requiere .env completo y Oracle XE activo)
python -m tests.db_health_test

# Pruebas de configuración inicial (validaciones + Oracle con ROLLBACK, no persiste datos)
python -m tests.bootstrap_test

# Pruebas de login/autenticación (Oracle con ROLLBACK, no persiste datos)
python -m tests.auth_test
```

## Estado del proyecto

| Objetivo | Descripción | Estado |
|---|---|---|
| 1 | Estructura y configuración del proyecto | ✅ Completado |
| 2 | Conexión Python → Oracle | ✅ Completado |
| 3 | Configuración inicial / primer ADMIN | ✅ Completado |
| 4 | Login y autenticación | ✅ Completado |
| 5 | Shell principal (sidebar, topbar, navegación) | Pendiente |
