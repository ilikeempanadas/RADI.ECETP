import os
import importlib
from datetime import date
from pathlib import Path
from typing import Optional, Union

try:
    load_dotenv = importlib.import_module("dotenv").load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        """Fallback cuando python-dotenv no está instalado."""
        return False
try:
    _fastapi = importlib.import_module("fastapi")
    FastAPI = _fastapi.FastAPI
    HTTPException = _fastapi.HTTPException
except ImportError:
    FastAPI = None
    HTTPException = None
try:
    FileResponse = importlib.import_module("fastapi.responses").FileResponse
except ImportError:
    FileResponse = None
try:
    BaseModel = importlib.import_module("pydantic").BaseModel
except ImportError:
    class BaseModel:
        """Fallback para permitir cargar el módulo sin Pydantic instalado."""

        pass

try:
    StaticFiles = importlib.import_module("fastapi.staticfiles").StaticFiles
except ImportError:
    StaticFiles = None

try:
    CORSMiddleware = importlib.import_module("fastapi.middleware.cors").CORSMiddleware
except ImportError:
    CORSMiddleware = None

# Se carga dinámicamente para que el editor no marque el módulo como
# inexistente cuando el intérprete seleccionado no tiene instalado PyMySQL.
try:
    pymysql = importlib.import_module("pymysql")
except ImportError:
    pymysql = None

# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Sistema de Gestión Académica - RADIxECETP API",
    description="API RESTful conectada a Aiven MySQL para control de notas y datos institucionales",
    version="1.0.0"
)

# Estáticos (CSS, JS, imágenes para los frontend HTML)
if StaticFiles is not None and (BASE_DIR / "css").is_dir():
    app.mount("/css", StaticFiles(directory=BASE_DIR / "css"), name="css")
if StaticFiles is not None and (BASE_DIR / "js").is_dir():
    app.mount("/js", StaticFiles(directory=BASE_DIR / "js"), name="js")
if StaticFiles is not None and (BASE_DIR / "images").is_dir():
    app.mount("/images", StaticFiles(directory=BASE_DIR / "images"), name="images")

if CORSMiddleware is not None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )


# ============================================================
# CONEXIÓN A AIVEN MYSQL
# ============================================================

def conectar():
    if pymysql is None:
        print("❌ PyMySQL no está instalado. Ejecuta: python -m pip install PyMySQL")
        return None
    try:
        conexion = pymysql.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=10,
            write_timeout=10
        )
        return conexion
    except Exception as e:
        print("❌ Error de conexión:", e)
        return None


# ============================================================
# FUNCIONES AUXILIARES SQL
# ============================================================

def consultar(sql, parametros=()):
    conexion = conectar()
    if conexion is None:
        raise HTTPException(status_code=500, detail="No se pudo conectar con Aiven MySQL")

    try:
        cursor = conexion.cursor()
        cursor.execute(sql, parametros)
        resultado = cursor.fetchall()
        cursor.close()
        conexion.close()
        return resultado
    except Exception as e:
        if conexion:
            conexion.close()
        print("❌ Error SQL:", e)
        raise HTTPException(status_code=500, detail=str(e))


def ejecutar(sql, parametros=()):
    conexion = conectar()
    if conexion is None:
        raise HTTPException(status_code=500, detail="No se pudo conectar con Aiven MySQL")

    try:
        cursor = conexion.cursor()
        cursor.execute(sql, parametros)
        conexion.commit()

        resultado = {
            "lastrowid": cursor.lastrowid,
            "filas_afectadas": cursor.rowcount
        }

        cursor.close()
        conexion.close()
        return resultado
    except Exception as e:
        if conexion:
            conexion.rollback()
            conexion.close()
        print("❌ Error SQL:", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# MODELOS DE DATOS INSTITUCIONALES (PYDANTIC)
# ============================================================

class Usuario(BaseModel):
    email: str
    contraseña: Optional[str] = None
    nombre_1: str
    nombre_2: Optional[str] = None
    apellido_1: str
    apellido_2: Optional[str] = None
    tp_documento: str
    num_documento: int
    rol: str  # Ej: 'Estudiante', 'Docente', 'Admin'


class Asignatura(BaseModel):
    nombre_asignatura: str
    codigo_materia: Optional[str] = None
    id_docente: Optional[int] = None


class Nota(BaseModel):
    id_estudiante: int
    id_asignatura: int
    descripcion: str  # Título o descripción del trabajo / actividad
    valor_nota: float  # Calificación del 0.0 al 5.0
    periodo: Optional[int] = 1
    fecha_registro: Optional[Union[str, date]] = None


# ============================================================
# RUTAS DE CONTROL
# ============================================================

@app.get("/", include_in_schema=False)
def inicio():
    index_path = BASE_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return {"mensaje": "API RADIxECETP - Sistema de Notas e Información Institucional"}


@app.get("/api/test-db")
def probar_bd():
    conexion = conectar()
    if conexion is None:
        raise HTTPException(status_code=500, detail="No se pudo conectar con Aiven")

    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT VERSION() AS version")
        resultado = cursor.fetchone()
        cursor.close()
        conexion.close()
        return {
            "conexion": "exitosa",
            "servidor": "Aiven MySQL",
            "version_mysql": resultado["version"]
        }
    except Exception as e:
        if conexion:
            conexion.close()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GESTIÓN DE USUARIOS INSTITUCIONALES (Estudiantes/Docentes)
# ============================================================

@app.get("/api/usuarios")
def listar_usuarios():
    sql = """
        SELECT
            id_usuario, email, nombre_1, nombre_2,
            apellido_1, apellido_2, tp_documento, num_documento, rol
        FROM usuarios
        ORDER BY apellido_1, nombre_1
    """
    return consultar(sql)


@app.get("/api/usuarios/{id_usuario}")
def obtener_usuario(id_usuario: int):
    sql = """
        SELECT
            id_usuario, email, nombre_1, nombre_2,
            apellido_1, apellido_2, tp_documento, num_documento, rol
        FROM usuarios
        WHERE id_usuario = %s
    """
    resultado = consultar(sql, (id_usuario,))
    if not resultado:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return resultado[0]


@app.post("/api/usuarios", status_code=201)
def crear_usuario(usuario: Usuario):
    sql = """
        INSERT INTO usuarios (
            email, contraseña, nombre_1, nombre_2,
            apellido_1, apellido_2, tp_documento, num_documento, rol
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    resultado = ejecutar(
        sql,
        (
            usuario.email, usuario.contraseña, usuario.nombre_1, usuario.nombre_2,
            usuario.apellido_1, usuario.apellido_2, usuario.tp_documento,
            usuario.num_documento, usuario.rol
        )
    )
    return {"mensaje": "Usuario registrado correctamente", "id_usuario": resultado["lastrowid"]}


@app.put("/api/usuarios/{id_usuario}")
def actualizar_usuario(id_usuario: int, usuario: Usuario):
    sql = """
        UPDATE usuarios
        SET
            email = %s, contraseña = %s, nombre_1 = %s, nombre_2 = %s,
            apellido_1 = %s, apellido_2 = %s, tp_documento = %s,
            num_documento = %s, rol = %s
        WHERE id_usuario = %s
    """
    resultado = ejecutar(
        sql,
        (
            usuario.email, usuario.contraseña, usuario.nombre_1, usuario.nombre_2,
            usuario.apellido_1, usuario.apellido_2, usuario.tp_documento,
            usuario.num_documento, usuario.rol, id_usuario
        )
    )
    if resultado["filas_afectadas"] == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"mensaje": "Datos de usuario actualizados correctamente"}


@app.delete("/api/usuarios/{id_usuario}")
def eliminar_usuario(id_usuario: int):
    sql = "DELETE FROM usuarios WHERE id_usuario = %s"
    resultado = ejecutar(sql, (id_usuario,))
    if resultado["filas_afectadas"] == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"mensaje": "Usuario eliminado del sistema"}


# ============================================================
# GESTIÓN DE ASIGNATURAS / MATERIAS
# ============================================================

@app.get("/api/asignaturas")
def listar_asignaturas():
    sql = """
        SELECT id_asignatura, nombre_asignatura, codigo_materia, id_docente
        FROM asignaturas
        ORDER BY nombre_asignatura
    """
    return consultar(sql)


@app.post("/api/asignaturas", status_code=201)
def crear_asignatura(asignatura: Asignatura):
    sql = "INSERT INTO asignaturas (nombre_asignatura, codigo_materia, id_docente) VALUES (%s, %s, %s)"
    resultado = ejecutar(sql, (asignatura.nombre_asignatura, asignatura.codigo_materia, asignatura.id_docente))
    return {"mensaje": "Asignatura creada correctamente", "id_asignatura": resultado["lastrowid"]}


# ============================================================
# GESTIÓN DE NOTAS Y EVALUACIONES
# ============================================================

@app.get("/api/notas")
def listar_notas():
    sql = """
        SELECT
            n.id_nota,
            CONCAT(u.nombre_1, ' ', u.apellido_1) AS estudiante,
            a.nombre_asignatura,
            n.descripcion,
            n.valor_nota,
            n.periodo,
            n.fecha_registro
        FROM notas n
        JOIN usuarios u ON n.id_estudiante = u.id_usuario
        JOIN asignaturas a ON n.id_asignatura = a.id_asignatura
        ORDER BY n.id_nota DESC
    """
    return consultar(sql)


@app.get("/api/notas/estudiante/{id_estudiante}")
def obtener_notas_estudiante(id_estudiante: int):
    sql = """
        SELECT
            n.id_nota,
            a.nombre_asignatura,
            n.descripcion,
            n.valor_nota,
            n.periodo,
            n.fecha_registro
        FROM notas n
        JOIN asignaturas a ON n.id_asignatura = a.id_asignatura
        WHERE n.id_estudiante = %s
        ORDER BY a.nombre_asignatura, n.periodo
    """
    return consultar(sql, (id_estudiante,))


@app.post("/api/notas", status_code=201)
def registrar_nota(nota: Nota):
    sql = """
        INSERT INTO notas (id_estudiante, id_asignatura, descripcion, valor_nota, periodo, fecha_registro)
        VALUES (%s, %s, %s, %s, %s, NOW())
    """
    resultado = ejecutar(sql, (nota.id_estudiante, nota.id_asignatura, nota.descripcion, nota.valor_nota, nota.periodo))
    return {"mensaje": "Nota registrada exitosamente", "id_nota": resultado["lastrowid"]}


@app.put("/api/notas/{id_nota}")
def actualizar_nota(id_nota: int, nota: Nota):
    sql = """
        UPDATE notas
        SET id_estudiante = %s, id_asignatura = %s, descripcion = %s, valor_nota = %s, periodo = %s
        WHERE id_nota = %s
    """
    resultado = ejecutar(sql, (nota.id_estudiante, nota.id_asignatura, nota.descripcion, nota.valor_nota, nota.periodo, id_nota))
    if resultado["filas_afectadas"] == 0:
        raise HTTPException(status_code=404, detail="Registro de nota no encontrado")
    return {"mensaje": "Nota actualizada correctamente"}


@app.delete("/api/notas/{id_nota}")
def eliminar_nota(id_nota: int):
    sql = "DELETE FROM notas WHERE id_nota = %s"
    resultado = ejecutar(sql, (id_nota,))
    if resultado["filas_afectadas"] == 0:
        raise HTTPException(status_code=404, detail="Nota no encontrada")
    return {"mensaje": "Nota eliminada del sistema"}


# ============================================================
# EJECUCIÓN DEL SERVIDOR
# ============================================================

if __name__ == "__main__":
    import importlib

    uvicorn = importlib.import_module("uvicorn")

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    print(f"\n🚀 Servidor RADIxECETP activo en: http://{host}:{port}")
    print("📚 Panel de Documentación interactivo: /docs\n")

    uvicorn.run(app, host=host, port=port)
    # ============================================================
# INFORMACIÓN DEL ADMINISTRADOR AUTENTICADO
# ============================================================

@app.get("/api/admin/perfil/{id_usuario}")
def obtener_perfil_admin(id_usuario: int):
    sql = """
        SELECT id_usuario, nombre_1, nombre_2, apellido_1, apellido_2, email, rol
        FROM usuarios
        WHERE id_usuario = %s AND rol = 'Admin'
    """
    resultado = consultar(sql, (id_usuario,))
    if not resultado:
        raise HTTPException(status_code=404, detail="Administrador no encontrado o sin permisos")
    
    admin = resultado[0]
    nombre_completo = f"{admin['nombre_1']} {admin['nombre_2'] or ''} {admin['apellido_1']} {admin['apellido_2'] or ''}".strip()
    return {
        "id_usuario": admin["id_usuario"],
        "nombre_completo": ' '.join(nombre_completo.split()),
        "email": admin["email"],
        "rol": admin["rol"]
    }