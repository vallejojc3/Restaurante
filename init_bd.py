"""
Script de inicialización de la base de datos
Ejecutar con: python init_db.py
También se ejecuta automáticamente en Railway al desplegar
"""

from app import app, db, Usuario, Mesa, CategoriaGasto, ConfiguracionRestaurante, Presupuesto
from datetime import datetime
import sys

def init_database():
    """
    Inicializa la base de datos con datos por defecto
    """
    try:
        with app.app_context():
            print("🔧 Creando/actualizando tablas de base de datos...")
            db.create_all()
            
            # =========================
            # USUARIOS POR DEFECTO
            # =========================
            usuarios_default = [
                {
                    'username': 'admin',
                    'password': 'admin123',
                    'nombre': 'Administrador',
                    'rol': 'admin'
                },
                {
                    'username': 'mesero1',
                    'password': 'mesero123',
                    'nombre': 'Mesero 1',
                    'rol': 'mesero'
                },
                {
                    'username': 'mesero2',
                    'password': 'mesero123',
                    'nombre': 'Mesero 2',
                    'rol': 'mesero'
                },
                {
                    'username': 'cocina',
                    'password': 'cocina123',
                    'nombre': 'Cocina',
                    'rol': 'cocina'
                }
            ]
            
            print("\n👥 Creando usuarios...")
            usuarios_creados = 0
            for user_data in usuarios_default:
                if not Usuario.query.filter_by(username=user_data['username']).first():
                    usuario = Usuario(
                        username=user_data['username'],
                        nombre=user_data['nombre'],
                        rol=user_data['rol']
                    )
                    usuario.set_password(user_data['password'])
                    db.session.add(usuario)
                    print(f"   ✓ Usuario creado: {user_data['username']} (rol: {user_data['rol']})")
                    usuarios_creados += 1
                else:
                    print(f"   ⚠ Usuario ya existe: {user_data['username']}")
            
            # =========================
            # MESAS
            # =========================
            print("\n🪑 Creando mesas...")
            if Mesa.query.count() == 0:
                for i in range(1, 11):
                    mesa = Mesa(numero=i, capacidad=4)
                    db.session.add(mesa)
                print(f"   ✓ Creadas 10 mesas (1-10)")
            else:
                print(f"   ⚠ Ya existen {Mesa.query.count()} mesas")
            
            # =========================
            # CATEGORÍAS DE GASTOS
            # =========================
            print("\n💰 Creando categorías de gastos...")
            if CategoriaGasto.query.count() == 0:
                categorias_default = [
                    {'nombre': 'Ingredientes y Materia Prima', 'descripcion': 'Compras de alimentos, bebidas y suministros de cocina', 'color': '#28a745'},
                    {'nombre': 'Salarios y Nómina', 'descripcion': 'Pagos a empleados, prestaciones y seguridad social', 'color': '#007bff'},
                    {'nombre': 'Servicios Públicos', 'descripcion': 'Agua, luz, gas, internet, teléfono', 'color': '#ffc107'},
                    {'nombre': 'Arriendo', 'descripcion': 'Pago de arriendo del local', 'color': '#dc3545'},
                    {'nombre': 'Mantenimiento', 'descripcion': 'Reparaciones, limpieza, mantenimiento de equipos', 'color': '#6c757d'},
                    {'nombre': 'Marketing', 'descripcion': 'Publicidad, redes sociales, volantes', 'color': '#e83e8c'},
                    {'nombre': 'Impuestos', 'descripcion': 'Impuestos, declaraciones, trámites legales', 'color': '#fd7e14'},
                    {'nombre': 'Otros Gastos', 'descripcion': 'Gastos misceláneos', 'color': '#6610f2'}
                ]
                
                for cat_data in categorias_default:
                    categoria = CategoriaGasto(**cat_data)
                    db.session.add(categoria)
                
                print(f"   ✓ Creadas {len(categorias_default)} categorías de gastos")
            else:
                print(f"   ⚠ Ya existen {CategoriaGasto.query.count()} categorías")
            
            # =========================
            # CONFIGURACIÓN DEL RESTAURANTE
            # =========================
            print("\n⚙️  Creando configuración del restaurante...")
            if ConfiguracionRestaurante.query.count() == 0:
                config = ConfiguracionRestaurante(
                    nombre='Ivaluth Restaurant',
                    nit='900.000.000-0',
                    direccion='Calle 123 #45-67',
                    ciudad='Zarzal, Valle del Cauca',
                    telefono='(+57) 300 000 0000',
                    regimen='Régimen Simplificado'
                )
                db.session.add(config)
                print("   ✓ Configuración creada")
            else:
                print("   ⚠ Configuración ya existe")
            
            # =========================
            # PRESUPUESTOS DE EJEMPLO
            # =========================
            print("\n🎯 Creando presupuestos de ejemplo...")
            if Presupuesto.query.count() == 0:
                mes_actual = datetime.now().month
                anio_actual = datetime.now().year
                
                # Obtener categorías
                cat_ingredientes = CategoriaGasto.query.filter_by(nombre='Ingredientes y Materia Prima').first()
                cat_salarios = CategoriaGasto.query.filter_by(nombre='Salarios y Nómina').first()
                cat_servicios = CategoriaGasto.query.filter_by(nombre='Servicios Públicos').first()
                
                presupuestos_creados = 0
                
                if cat_ingredientes:
                    presupuesto = Presupuesto(
                        categoria_id=cat_ingredientes.id,
                        monto_limite=2000000,  # $2,000,000
                        periodo='mensual',
                        mes=mes_actual,
                        anio=anio_actual,
                        alerta_porcentaje=80
                    )
                    db.session.add(presupuesto)
                    presupuestos_creados += 1
                
                if cat_salarios:
                    presupuesto = Presupuesto(
                        categoria_id=cat_salarios.id,
                        monto_limite=3000000,  # $3,000,000
                        periodo='mensual',
                        mes=mes_actual,
                        anio=anio_actual,
                        alerta_porcentaje=90
                    )
                    db.session.add(presupuesto)
                    presupuestos_creados += 1
                
                if cat_servicios:
                    presupuesto = Presupuesto(
                        categoria_id=cat_servicios.id,
                        monto_limite=500000,  # $500,000
                        periodo='mensual',
                        mes=mes_actual,
                        anio=anio_actual,
                        alerta_porcentaje=75
                    )
                    db.session.add(presupuesto)
                    presupuestos_creados += 1
                
                if presupuestos_creados > 0:
                    print(f"   ✓ Creados {presupuestos_creados} presupuestos")
                else:
                    print("   ⚠ No se pudieron crear presupuestos (faltan categorías)")
            else:
                print(f"   ⚠ Ya existen {Presupuesto.query.count()} presupuestos")
            
            # =========================
            # GUARDAR CAMBIOS
            # =========================
            db.session.commit()
            
            print("\n" + "="*60)
            print("✅ BASE DE DATOS INICIALIZADA CORRECTAMENTE")
            print("="*60)
            
            print("\n📊 SISTEMA DE GESTIÓN DE RESTAURANTE")
            print("   • Sesiones por mesa para mejor control")
            print("   • Facturación electrónica")
            print("   • Control de gastos y presupuestos")
            print("   • Gestión de domicilios")
            print("   • Reportes financieros")
            
            print("\n📋 USUARIOS DISPONIBLES:")
            print("   • admin / admin123 (Administrador)")
            print("   • mesero1 / mesero123 (Mesero)")
            print("   • mesero2 / mesero123 (Mesero)")
            print("   • cocina / cocina123 (Cocina)")
            
            print("\n⚠️  IMPORTANTE: Cambia estas contraseñas en producción!")
            print("\n🚀 Próximo paso: python app.py o desplegar en Railway")
            print("="*60 + "\n")
            
            return True
            
    except Exception as e:
        print(f"\n❌ ERROR al inicializar base de datos:")
        print(f"   {str(e)}")
        print("\n💡 Posibles causas:")
        print("   1. La base de datos no está accesible")
        print("   2. Falta la variable DATABASE_URL")
        print("   3. Las credenciales de PostgreSQL son incorrectas")
        db.session.rollback()
        return False

def verificar_estado():
    """
    Verifica el estado de la base de datos
    """
    try:
        with app.app_context():
            print("\n🔍 Verificando estado de la base de datos...")
            
            usuarios = Usuario.query.count()
            mesas = Mesa.query.count()
            categorias = CategoriaGasto.query.count()
            presupuestos = Presupuesto.query.count()
            
            print(f"   👥 Usuarios: {usuarios}")
            print(f"   🪑 Mesas: {mesas}")
            print(f"   💰 Categorías de gastos: {categorias}")
            print(f"   🎯 Presupuestos: {presupuestos}")
            
            if usuarios > 0 and mesas > 0:
                print("\n✅ Base de datos configurada correctamente")
                return True
            else:
                print("\n⚠️  Base de datos vacía o incompleta")
                return False
                
    except Exception as e:
        print(f"\n❌ Error al verificar base de datos: {str(e)}")
        return False

if __name__ == "__main__":
    # Verificar si se pasó el argumento --verify
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        verificar_estado()
    else:
        # Inicializar base de datos
        exito = init_database()
        
        if exito:
            sys.exit(0)  # Código de salida 0 = éxito
        else:
            sys.exit(1)  # Código de salida 1 = error