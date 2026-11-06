// Optional: pre-creates indexes in mongosh. The backend also does this automatically on start.
//   mongosh "mongodb://127.0.0.1:27017" database/init_mongo.js
db = db.getSiblingDB('medismart');

try { db.getCollection('users').createIndex({ 'email': 1 }, { unique: true }); } catch (e) { print('index warning on users: ' + e.message); }
try { db.getCollection('users').createIndex({ 'id': 1 }, { unique: true }); } catch (e) { print('index warning on users: ' + e.message); }
try { db.getCollection('patients').createIndex({ 'user_id': 1 }, { unique: true }); } catch (e) { print('index warning on patients: ' + e.message); }
try { db.getCollection('patients').createIndex({ 'health_id': 1 }, { unique: true }); } catch (e) { print('index warning on patients: ' + e.message); }
try { db.getCollection('vitals').createIndex({ 'patient_id': 1, 'ts': -1 }, {}); } catch (e) { print('index warning on vitals: ' + e.message); }
try { db.getCollection('appointments').createIndex({ 'doctor_id': 1, 'date': 1 }, {}); } catch (e) { print('index warning on appointments: ' + e.message); }
try { db.getCollection('appointments').createIndex({ 'patient_user_id': 1, 'date': 1 }, {}); } catch (e) { print('index warning on appointments: ' + e.message); }
try { db.getCollection('audit_logs').createIndex({ 'ts': -1 }, {}); } catch (e) { print('index warning on audit_logs: ' + e.message); }
try { db.getCollection('notifications').createIndex({ 'user_id': 1, 'ts': -1 }, {}); } catch (e) { print('index warning on notifications: ' + e.message); }
try { db.getCollection('events').createIndex({ 'user_id': 1, 'ts': -1 }, {}); } catch (e) { print('index warning on events: ' + e.message); }
try { db.getCollection('vital_alerts').createIndex({ 'patient_id': 1, 'ts': -1 }, {}); } catch (e) { print('index warning on vital_alerts: ' + e.message); }
try { db.getCollection('med_orders').createIndex({ 'user_id': 1, 'created_at': -1 }, {}); } catch (e) { print('index warning on med_orders: ' + e.message); }
try { db.getCollection('med_orders').createIndex({ 'pharmacy_id': 1 }, {}); } catch (e) { print('index warning on med_orders: ' + e.message); }
try { db.getCollection('pharmacy_stock').createIndex({ 'user_id': 1, 'name': 1 }, {}); } catch (e) { print('index warning on pharmacy_stock: ' + e.message); }
try { db.getCollection('medicines').createIndex({ 'user_id': 1, 'active': 1 }, {}); } catch (e) { print('index warning on medicines: ' + e.message); }
try { db.getCollection('med_logs').createIndex({ 'user_id': 1, 'date': 1 }, {}); } catch (e) { print('index warning on med_logs: ' + e.message); }
try { db.getCollection('reports').createIndex({ 'user_id': 1, 'ts': -1 }, {}); } catch (e) { print('index warning on reports: ' + e.message); }
try { db.getCollection('risk_assessments').createIndex({ 'user_id': 1, 'ts': -1 }, {}); } catch (e) { print('index warning on risk_assessments: ' + e.message); }
try { db.getCollection('ledger_blocks').createIndex({ 'chain': 1, 'index': 1 }, { unique: true }); } catch (e) { print('index warning on ledger_blocks: ' + e.message); }
try { db.getCollection('wearable_samples').createIndex({ 'k': 1 }, { unique: true }); } catch (e) { print('index warning on wearable_samples: ' + e.message); }
try { db.getCollection('board_cases').createIndex({ 'patient_id': 1 }, {}); } catch (e) { print('index warning on board_cases: ' + e.message); }
try { db.getCollection('board_cases').createIndex({ 'panel.doctor_user_id': 1 }, {}); } catch (e) { print('index warning on board_cases: ' + e.message); }
try { db.getCollection('fl_models').createIndex({ 'disease': 1 }, { unique: true }); } catch (e) { print('index warning on fl_models: ' + e.message); }
try { db.getCollection('fl_rounds').createIndex({ 'disease': 1, 'status': 1 }, {}); } catch (e) { print('index warning on fl_rounds: ' + e.message); }
try { db.getCollection('ews_state').createIndex({ 'user_id': 1 }, { unique: true }); } catch (e) { print('index warning on ews_state: ' + e.message); }
try { db.getCollection('ews_settings').createIndex({ 'user_id': 1 }, { unique: true }); } catch (e) { print('index warning on ews_settings: ' + e.message); }
try { db.getCollection('ews_events').createIndex({ 'user_id': 1, 'ts': -1 }, {}); } catch (e) { print('index warning on ews_events: ' + e.message); }
try { db.getCollection('otps').createIndex({ 'email': 1, 'purpose': 1 }, {}); } catch (e) { print('index warning on otps: ' + e.message); }
try { db.getCollection('users').createIndex({ 'role': 1 }, {}); } catch (e) { print('index warning on users: ' + e.message); }
try { db.getCollection('revoked_tokens').createIndex({ 'jti': 1 }, { unique: true }); } catch (e) { print('index warning on revoked_tokens: ' + e.message); }
print('MediSmart indexes ready.');
