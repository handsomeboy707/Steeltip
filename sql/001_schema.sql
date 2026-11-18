USE steeltip;
CREATE TABLE users(id CHAR(36) PRIMARY KEY,username VARCHAR(80) NOT NULL UNIQUE,password_hash VARCHAR(200) NOT NULL,role ENUM('organiser','scorer','viewer') NOT NULL) ENGINE=InnoDB;
CREATE TABLE sessions(id CHAR(64) PRIMARY KEY,user_id CHAR(36) NOT NULL,expires_at DATETIME(6) NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE) ENGINE=InnoDB;
CREATE TABLE players(id CHAR(36) PRIMARY KEY,name VARCHAR(120) NOT NULL,email VARCHAR(254),archived BOOLEAN NOT NULL DEFAULT 0,provenance ENUM('synthetic','consented') NOT NULL, CHECK(CHAR_LENGTH(TRIM(name))>0)) ENGINE=InnoDB;
CREATE TABLE tournaments(id CHAR(36) PRIMARY KEY,name VARCHAR(160) NOT NULL,start_date DATE NOT NULL,archived BOOLEAN NOT NULL DEFAULT 0,CHECK(CHAR_LENGTH(TRIM(name))>0)) ENGINE=InnoDB;
CREATE TABLE divisions(id CHAR(36) PRIMARY KEY,tournament_id CHAR(36) NOT NULL,name VARCHAR(80) NOT NULL,cap DECIMAL(9,4) NOT NULL,tolerance DECIMAL(9,4) NOT NULL,rule_version VARCHAR(30) NOT NULL,
 FOREIGN KEY(tournament_id) REFERENCES tournaments(id),UNIQUE(tournament_id,name),CHECK(cap>=0),CHECK(tolerance>=0)) ENGINE=InnoDB;
CREATE TABLE registrations(id CHAR(36) PRIMARY KEY,player_id CHAR(36) NOT NULL,division_id CHAR(36) NOT NULL,declared_rating DECIMAL(9,4) NOT NULL,
 UNIQUE(player_id,division_id),FOREIGN KEY(player_id) REFERENCES players(id),FOREIGN KEY(division_id) REFERENCES divisions(id),CHECK(declared_rating>=0)) ENGINE=InnoDB;
CREATE TABLE matches(id CHAR(36) PRIMARY KEY,division_id CHAR(36) NOT NULL,player1_id CHAR(36) NOT NULL,player2_id CHAR(36) NOT NULL,
 FOREIGN KEY(division_id) REFERENCES divisions(id),FOREIGN KEY(player1_id,division_id) REFERENCES registrations(player_id,division_id),FOREIGN KEY(player2_id,division_id) REFERENCES registrations(player_id,division_id),CHECK(player1_id<>player2_id)) ENGINE=InnoDB;
CREATE TABLE legs(id CHAR(36) PRIMARY KEY,match_id CHAR(36) NOT NULL,number INT NOT NULL,accepted_revision CHAR(36),accepted_number INT NOT NULL DEFAULT 0,
 FOREIGN KEY(match_id) REFERENCES matches(id),UNIQUE(match_id,number),CHECK(number>0),CHECK(accepted_number>=0)) ENGINE=InnoDB;
CREATE TABLE revisions(id CHAR(36) PRIMARY KEY,leg_id CHAR(36) NOT NULL,number INT NOT NULL,digest CHAR(64) NOT NULL,accepted_by CHAR(36) NOT NULL,created_at DATETIME(6) NOT NULL,
 FOREIGN KEY(leg_id) REFERENCES legs(id),FOREIGN KEY(accepted_by) REFERENCES users(id),UNIQUE(leg_id,number),UNIQUE(id,leg_id),CHECK(number>0)) ENGINE=InnoDB;
ALTER TABLE legs ADD CONSTRAINT fk_accepted_revision FOREIGN KEY(accepted_revision,id) REFERENCES revisions(id,leg_id);
CREATE TABLE results(id CHAR(36) PRIMARY KEY,leg_id CHAR(36) NOT NULL,revision_id CHAR(36) NOT NULL,player_id CHAR(36) NOT NULL,
 points INT NOT NULL,darts INT NOT NULL,busts INT NOT NULL,eligible BOOLEAN NOT NULL,winner BOOLEAN NOT NULL,
 UNIQUE(player_id,leg_id,revision_id),FOREIGN KEY(revision_id,leg_id) REFERENCES revisions(id,leg_id),FOREIGN KEY(player_id) REFERENCES players(id),
 CHECK(points BETWEEN 0 AND 501),CHECK(darts>=0),CHECK(busts>=0),CHECK(eligible IN(0,1)),CHECK(winner IN(0,1)),CHECK(eligible=0 OR darts>0)) ENGINE=InnoDB;
CREATE TABLE snapshots(id CHAR(36) PRIMARY KEY,revision_id CHAR(36) NOT NULL,player_id CHAR(36) NOT NULL,cap DECIMAL(9,4) NOT NULL,tolerance DECIMAL(9,4) NOT NULL,rule_version VARCHAR(30) NOT NULL,rating DECIMAL(16,8),breached BOOLEAN NOT NULL,
 UNIQUE(revision_id,player_id),FOREIGN KEY(revision_id) REFERENCES revisions(id),FOREIGN KEY(player_id) REFERENCES players(id),CHECK(cap>=0),CHECK(tolerance>=0),CHECK(rating IS NULL OR rating>=0)) ENGINE=InnoDB;
CREATE TABLE reviews(id CHAR(36) PRIMARY KEY,revision_id CHAR(36) NOT NULL,player_id CHAR(36) NOT NULL,status ENUM('pending','confirmed','dismissed','superseded') NOT NULL,note VARCHAR(1000),reviewed_by CHAR(36),reviewed_at DATETIME(6),
 UNIQUE(revision_id,player_id),FOREIGN KEY(revision_id,player_id) REFERENCES snapshots(revision_id,player_id),FOREIGN KEY(reviewed_by) REFERENCES users(id)) ENGINE=InnoDB;
CREATE TABLE audits(id CHAR(36) PRIMARY KEY,user_id CHAR(36) NOT NULL,action VARCHAR(80) NOT NULL,entity_id VARCHAR(80) NOT NULL,details TEXT NOT NULL,created_at DATETIME(6) NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id)) ENGINE=InnoDB;
CREATE INDEX idx_results_revision ON results(revision_id,player_id);
CREATE INDEX idx_review_status ON reviews(status,revision_id);
CREATE INDEX idx_sessions_expiry ON sessions(expires_at);
CREATE VIEW accepted_results AS SELECT r.*,m.division_id,v.created_at,
 CASE WHEN r.eligible AND r.darts>0 THEN 3.0*r.points/r.darts ELSE NULL END AS rating
 FROM results r JOIN legs l ON l.id=r.leg_id AND l.accepted_revision=r.revision_id
 JOIN matches m ON m.id=l.match_id JOIN revisions v ON v.id=r.revision_id;
