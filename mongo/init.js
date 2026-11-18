const database=db.getSiblingDB('steeltip');
const uuid={bsonType:'string',pattern:'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'};
const dart={bsonType:'object',required:['segment','multiplier'],additionalProperties:false,properties:{
 segment:{bsonType:'int',enum:[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,25]},
 multiplier:{bsonType:'int',minimum:1,maximum:3}}};
const visit={bsonType:'object',required:['player_id','darts'],additionalProperties:false,properties:{player_id:uuid,darts:{bsonType:'array',minItems:1,maxItems:3,items:dart}}};
const properties={_id:uuid,leg_id:uuid,revision:{bsonType:'int',minimum:1},base_revision:{bsonType:'int',minimum:0},
 players:{bsonType:'array',minItems:2,maxItems:2,uniqueItems:true,items:uuid},status:{enum:['completed','abandoned']},
 visits:{bsonType:'array',maxItems:1000,items:visit},created_by:uuid};
const required=['_id','leg_id','revision','base_revision','players','status','visits','created_by'];
database.createCollection('drafts',{validator:{$jsonSchema:{bsonType:'object',additionalProperties:false,
 required:[...required,'version','state'],properties:{...properties,version:{bsonType:'int',minimum:0},state:{enum:['draft','frozen']}}}},validationAction:'error',validationLevel:'strict'});
database.createCollection('revisions',{validator:{$jsonSchema:{bsonType:'object',additionalProperties:false,
 required:[...required,'digest','derived','created_at'],properties:{...properties,digest:{bsonType:'string',pattern:'^[a-f0-9]{64}$'},
 created_at:{bsonType:'string'},derived:{bsonType:'object',required:['status','winner_id','results','replay'],properties:{
 status:{enum:['completed','abandoned']},winner_id:{bsonType:['string','null']},results:{bsonType:'array',minItems:2,maxItems:2},replay:{bsonType:'array'}}}}}},validationAction:'error',validationLevel:'strict'});
database.revisions.createIndex({leg_id:1,revision:1},{unique:true,name:'unique_leg_revision'});
database.drafts.createIndex({leg_id:1});
database.createRole({role:'steeltipApplication',roles:[],privileges:[
 {resource:{db:'steeltip',collection:'drafts'},actions:['find','insert','update','remove']},
 {resource:{db:'steeltip',collection:'revisions'},actions:['find','insert','listIndexes']} ]});
database.createUser({user:'steeltip_app',pwd:process.env.MONGO_APP_PASSWORD,roles:[{role:'steeltipApplication',db:'steeltip'}]});
