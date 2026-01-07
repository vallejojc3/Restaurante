import os
import sys

# Asegurarse de que podemos importar desde app.py
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db, Usuario, Mesa, CategoriaGasto, ConfiguracionRestaurante

def initialize_database():
    """Inicializa la base de datos con todos los datos necesarios"""
    
    print("\n" + "="*60)
    print("  INICIALIZANDO BASE DE DATOS")
    print("="*60 + "\n")
    
    with app.app_context():
        try:
            # Crear todas las tablas
            print("📦 Creando tablas...")
            db.create_all()
            print("✅ Tablas creadas\n")
            
            # Verificar si ya hay usuarios
            usuario_count = Usuario.query.count()
            if usuario_count > 0:
                print(f"⚠️  Ya existen {usuario_count} usuarios")
                print("✅ Base de datos ya inicializada\n")
                return
            
            # CREAR USUARIOS
            print("👥 Creando usuarios...")
            
            admin = Usuario(username='admin', nombre='Administrador', rol='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            print("  ✓ admin / admin123")
            
            mesero = Usuario(username='mesero1', nombre='Mesero 1', rol='mesero')
            mesero.set_password('mesero123')
            db.session.add(mesero)
            print("  ✓ mesero1 / mesero123")
            
            cocina = Usuario(username='cocina', nombre='Cocina', rol='cocina')
            cocina.set_password('cocina123')
            db.session.add(cocina)
            print("  ✓ cocina / cocina123\n")
            
            # CREAR MESAS
            print("🪑 Creando mesas...")
            for i in range(1, 11):
                mesa = Mesa(numero=i, capacidad=4)
                db.session.add(mesa)
            print("  ✓ 10 mesas (1-10)\n")
            
            # CREAR CATEGORÍAS DE GASTOS
            print("📊 Creando categorías de gastos...")
            categorias = [
                {'nombre': 'Ingredientes y Materia Prima', 'color': '#28a745'},
                {'nombre': 'Salarios y Nómina', 'color': '#007bff'},
                {'nombre': 'Servicios Públicos', 'color': '#ffc107'},
                {'nombre': 'Arriendo', 'color': '#dc3545'},
                {'nombre': 'Mantenimiento', 'color': '#6c757d'},
                {'nombre': 'Marketing', 'color': '#e83e8c'},
                {'nombre': 'Impuestos', 'color': '#fd7e14'},
                {'nombre': 'Otros Gastos', 'color': '#6610f2'}
            ]
            
            for cat in categorias:
                categoria = CategoriaGasto(
                    nombre=cat['nombre'],
                    color=cat['color'],
                    activa=True
                )
                db.session.add(categoria)
            print(f"  ✓ {len(categorias)} categorías creadas\n")
            
            # CREAR CONFIGURACIÓN DEL RESTAURANTE
            print("⚙️  Creando configuración...")
            config = ConfiguracionRestaurante(
                nombre='Mi Restaurante',
                nit='900.000.000-0',
                direccion='Calle 123 #45-67',
                ciudad='Zarzal, Valle del Cauca',
                telefono='(+57) 300 000 0000',
                regimen='Régimen Simplificado'
            )
            db.session.add(config)
            print("  ✓ Configuración inicial creada\n")
            
            # GUARDAR TODO
            print("💾 Guardando cambios...")
            db.session.commit()
            
            print("\n" + "="*60)
            print("  ✅ BASE DE DATOS INICIALIZADA CORRECTAMENTE")
            print("="*60)
            print("\n📝 CREDENCIALES DE ACCESO:")
            print("  • Admin:  admin / admin123")
            print("  • Mesero: mesero1 / mesero123")
            print("  • Cocina: cocina / cocina123\n")
            
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}\n")
            db.session.rollback()
            raise


if __name__ == '__main__':
    initialize_database()