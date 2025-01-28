import logging
import logging.config
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_migrate import Migrate
from database import db, APIKey, Project
from datetime import datetime

logging.config.fileConfig('logging.conf')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///keys.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your-secret-key-here'

db.init_app(app)
migrate = Migrate(app, db)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/keys/<int:key_id>', methods=['GET'])
def get_key(key_id):
    try:
        key = APIKey.query.get_or_404(key_id)
        return jsonify(key.to_dict())
    except Exception as e:
        logger.error(f"Error fetching key {key_id}: {str(e)}")
        return jsonify({'error': 'Key not found'}), 404

@app.route('/keys', methods=['GET'])
def get_keys():
    try:
        logger.info("Fetching all keys from database...")
        # Get project_id from query params if it exists
        project_id = request.args.get('project_id', type=int)
        
        # Build query
        query = APIKey.query
        if project_id is not None:
            query = query.filter_by(project_id=project_id)
        elif project_id is None and request.args.get('show_all') != 'true':
            # If no project specified and not showing all, show only unassigned keys
            query = query.filter_by(project_id=None)
            
        # Order by position within each project
        keys = query.order_by(APIKey.project_id, APIKey.position).all()
        
        logger.info(f"Found {len(keys)} keys")
        result = [key.to_dict() for key in keys]
        logger.info("Successfully serialized keys to JSON")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching keys: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({'error': f'Failed to fetch keys: {str(e)}'}), 500

def generate_unique_name(base_name, project_id=None):
    """Generate a unique name by adding a numeric suffix if needed."""
    name = base_name
    counter = 1
    while True:
        existing = APIKey.query.filter_by(name=name, project_id=project_id).first()
        if not existing:
            return name
        name = f"{base_name}{counter}"
        counter += 1

@app.route('/keys', methods=['POST'])
def add_key():
    try:
        data = request.get_json()
        if not data or 'name' not in data or 'key' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
        
        project_id = data.get('project_id')
        unique_name = generate_unique_name(data['name'], project_id)
        
        # Get the maximum position for the project
        max_position = db.session.query(db.func.max(APIKey.position)).filter(
            APIKey.project_id == project_id
        ).scalar() or -1
            
        new_key = APIKey(
            name=unique_name,
            key=data['key'],
            description=data.get('description'),
            used_with=data.get('used_with'),
            project_id=project_id,
            position=max_position + 1
        )
        
        db.session.add(new_key)
        db.session.commit()
        logger.info(f"Added new key: {unique_name}")
        return jsonify(new_key.to_dict()), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding key: {str(e)}")
        return jsonify({'error': 'Failed to add key'}), 500

@app.route('/keys/<int:key_id>', methods=['DELETE'])
def delete_key(key_id):
    try:
        key = APIKey.query.get_or_404(key_id)
        db.session.delete(key)
        db.session.commit()
        logger.info(f"Deleted key: {key.name}")
        return jsonify({'message': 'Key deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting key: {str(e)}")
        return jsonify({'error': 'Failed to delete key'}), 500

@app.route('/keys/<int:key_id>', methods=['PUT'])
def update_key(key_id):
    try:
        key = APIKey.query.get_or_404(key_id)
        data = request.get_json()
        
        if 'name' in data and data['name'] != key.name:
            unique_name = generate_unique_name(data['name'], data.get('project_id', key.project_id))
            key.name = unique_name
        if 'key' in data:
            key.key = data['key']
        if 'description' in data:
            key.description = data['description']
        if 'used_with' in data:
            key.used_with = data['used_with']
        if 'project_id' in data:
            key.project_id = data['project_id']
            # If project changed, check if name needs to be updated
            if key.project_id != data['project_id']:
                key.name = generate_unique_name(key.name, data['project_id'])
            
        db.session.commit()
        logger.info(f"Updated key: {key.name}")
        return jsonify(key.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating key: {str(e)}")
        return jsonify({'error': 'Failed to update key'}), 500

@app.route('/projects', methods=['GET'])
def get_projects():
    try:
        projects = Project.query.all()
        return jsonify([project.to_dict() for project in projects])
    except Exception as e:
        logger.error(f"Error fetching projects: {str(e)}")
        return jsonify({'error': 'Failed to fetch projects'}), 500

@app.route('/projects', methods=['POST'])
def create_project():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Project name required'}), 400
            
        new_project = Project(name=data['name'])
        db.session.add(new_project)
        db.session.commit()
        return jsonify(new_project.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating project: {str(e)}")
        return jsonify({'error': 'Failed to create project'}), 500

@app.route('/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        db.session.delete(project)
        db.session.commit()
        return jsonify({'message': 'Project deleted'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting project: {str(e)}")
        return jsonify({'error': 'Failed to delete project'}), 500

@app.route('/keys/<int:key_id>/project', methods=['PATCH'])
def update_key_project(key_id):
    try:
        key = APIKey.query.get_or_404(key_id)
        data = request.get_json()
        key.project_id = data.get('project_id')
        db.session.commit()
        return jsonify(key.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating key project: {str(e)}")
        return jsonify({'error': 'Failed to update project'}), 500

@app.route('/projects/<int:project_id>', methods=['PUT'])
def update_project(project_id):
    try:
        project = Project.query.get_or_404(project_id)
        data = request.get_json()
        
        if 'name' in data:
            if Project.query.filter(Project.id != project_id, Project.name == data['name']).first():
                return jsonify({'error': 'Project name already exists'}), 409
            project.name = data['name']
            
        db.session.commit()
        logger.info(f"Updated project: {project.name}")
        return jsonify(project.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating project: {str(e)}")
        return jsonify({'error': 'Failed to update project'}), 500

@app.route('/keys/<int:key_id>/reorder', methods=['PATCH'])
def reorder_key(key_id):
    try:
        data = request.get_json()
        if 'new_position' not in data:
            return jsonify({'error': 'New position is required'}), 400

        key = APIKey.query.get_or_404(key_id)
        new_position = data['new_position']
        old_position = key.position
        target_project_id = data.get('project_id', key.project_id)  # Default to current project if not specified

        logger.info(f"Reordering key {key.name} from position {old_position} to {new_position}")
        logger.info(f"Project change: {key.project_id} -> {target_project_id}")

        with db.session.begin_nested():  # Create a savepoint
            if target_project_id == key.project_id and new_position >= 0:
                # Moving within the same project
                if new_position > old_position:
                    # Moving forward: update positions of keys between old and new position
                    affected = APIKey.query.filter(
                        APIKey.project_id == target_project_id,
                        APIKey.position <= new_position,
                        APIKey.position > old_position,
                        APIKey.id != key_id
                    ).update({APIKey.position: APIKey.position - 1})
                    logger.info(f"Updated {affected} keys moving forward")
                else:
                    # Moving backward: update positions of keys between new and old position
                    affected = APIKey.query.filter(
                        APIKey.project_id == target_project_id,
                        APIKey.position >= new_position,
                        APIKey.position < old_position,
                        APIKey.id != key_id
                    ).update({APIKey.position: APIKey.position + 1})
                    logger.info(f"Updated {affected} keys moving backward")
            else:
                # Moving to a different project or to the end of current project
                # Close the gap in the old project if changing projects
                if target_project_id != key.project_id:
                    affected_old = APIKey.query.filter(
                        APIKey.project_id == key.project_id,
                        APIKey.position > old_position
                    ).update({APIKey.position: APIKey.position - 1})
                    logger.info(f"Updated {affected_old} keys in old project")

                # Get max position in target project
                max_position = db.session.query(db.func.max(APIKey.position)).filter(
                    APIKey.project_id == target_project_id
                ).scalar() or -1
                
                # Set new position to end of target project
                new_position = max_position + 1
                key.project_id = target_project_id

            key.position = new_position
            db.session.flush()  # Ensure all position updates are applied

            # Normalize positions within the affected projects
            for project_id in {key.project_id, target_project_id}:
                if project_id is not None:
                    keys = APIKey.query.filter_by(project_id=project_id).order_by(APIKey.position).all()
                    for i, k in enumerate(keys):
                        if k.position != i:
                            k.position = i
                            logger.info(f"Fixed position for key {k.name}: {k.position} -> {i}")

        db.session.commit()
        logger.info(f"Successfully reordered key {key.name} to position {new_position}")
        return jsonify(key.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error reordering key: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({'error': f'Failed to reorder key: {str(e)}'}), 500

@app.cli.command("check-db")
def check_db():
    """Check database tables and schema."""
    try:
        with app.app_context():
            # Check if tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"Found tables: {tables}")
            
            # Check APIKey table structure
            if 'api_key' in tables:
                columns = inspector.get_columns('api_key')
                print("\nAPIKey table structure:")
                for col in columns:
                    print(f"Column: {col['name']} ({col['type']})")
            
            # Count records
            keys_count = APIKey.query.count()
            projects_count = Project.query.count()
            print(f"\nFound {keys_count} keys and {projects_count} projects")
            
    except Exception as e:
        print(f"Error checking database: {str(e)}")
        raise

if __name__ == '__main__':
    app.run(host='localhost', port=5000, debug=True)# Main application file 