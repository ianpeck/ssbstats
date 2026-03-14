-- Scheduling and automation support tables for SSB Stats.
-- These tables are designed to mirror the legacy Fight / Results model where useful,
-- while adding enough metadata for booking, automation, and media linkage.

CREATE TABLE IF NOT EXISTS scheduled_matches (
    scheduled_match_id INT NOT NULL AUTO_INCREMENT,
    season_id INT NOT NULL,
    month TINYINT NOT NULL,
    week TINYINT NOT NULL,
    brand_id INT NOT NULL,
    match_order INT NOT NULL,
    scheduled_start_at DATETIME NULL,
    location_id INT NOT NULL,
    ppv_id INT NULL,
    championship_id INT NULL,
    fight_type_id INT NOT NULL,
    contender_indicator TINYINT(1) NOT NULL DEFAULT 0,
    status ENUM(
        'queued',
        'claimed',
        'running',
        'awaiting_result',
        'completed',
        'failed',
        'cancelled'
    ) NOT NULL DEFAULT 'queued',
    fight_id INT NULL,
    claimed_by VARCHAR(255) NULL,
    claimed_at DATETIME NULL,
    started_at DATETIME NULL,
    completed_at DATETIME NULL,
    retry_count INT NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    notes TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (scheduled_match_id),
    KEY idx_scheduled_matches_queue (season_id, month, week, brand_id, match_order),
    KEY idx_scheduled_matches_status_time (status, scheduled_start_at),
    KEY idx_scheduled_matches_fight_id (fight_id),
    CONSTRAINT fk_scheduled_matches_season
        FOREIGN KEY (season_id) REFERENCES Season (Season_ID),
    CONSTRAINT fk_scheduled_matches_brand
        FOREIGN KEY (brand_id) REFERENCES Brand (Brand_ID),
    CONSTRAINT fk_scheduled_matches_location
        FOREIGN KEY (location_id) REFERENCES Location (Location_ID),
    CONSTRAINT fk_scheduled_matches_ppv
        FOREIGN KEY (ppv_id) REFERENCES PPV (PPV_ID),
    CONSTRAINT fk_scheduled_matches_championship
        FOREIGN KEY (championship_id) REFERENCES Championship (Championship_ID),
    CONSTRAINT fk_scheduled_matches_fight_type
        FOREIGN KEY (fight_type_id) REFERENCES FightType (FightType_ID),
    CONSTRAINT fk_scheduled_matches_fight
        FOREIGN KEY (fight_id) REFERENCES Fight (Fight_ID)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS scheduled_match_participants (
    scheduled_match_participant_id INT NOT NULL AUTO_INCREMENT,
    scheduled_match_id INT NOT NULL,
    slot_number TINYINT NOT NULL,
    fighter_name VARCHAR(255) NOT NULL,
    team_id TINYINT NULL,
    team_color VARCHAR(32) NULL,
    cpu_level TINYINT NOT NULL,
    cpu_level_source ENUM('manual', 'elo_suggested') NOT NULL DEFAULT 'manual',
    seed INT NULL,
    defending_indicator TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (scheduled_match_participant_id),
    UNIQUE KEY uq_scheduled_match_participants_slot (scheduled_match_id, slot_number),
    KEY idx_scheduled_match_participants_fighter (fighter_name),
    CONSTRAINT fk_scheduled_match_participants_match
        FOREIGN KEY (scheduled_match_id) REFERENCES scheduled_matches (scheduled_match_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_scheduled_match_participants_fighter
        FOREIGN KEY (fighter_name) REFERENCES Fighter (Fighter_Name)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS contenderships (
    contendership_id INT NOT NULL AUTO_INCREMENT,
    championship_id INT NOT NULL,
    brand_id INT NOT NULL,
    fighter_name VARCHAR(255) NOT NULL,
    season_id INT NOT NULL,
    month TINYINT NOT NULL,
    earned_from_scheduled_match_id INT NULL,
    earned_from_fight_id INT NULL,
    status ENUM('active', 'used', 'revoked', 'expired') NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (contendership_id),
    KEY idx_contenderships_title_cycle (championship_id, brand_id, season_id, month, status),
    KEY idx_contenderships_fighter (fighter_name),
    CONSTRAINT fk_contenderships_championship
        FOREIGN KEY (championship_id) REFERENCES Championship (Championship_ID),
    CONSTRAINT fk_contenderships_brand
        FOREIGN KEY (brand_id) REFERENCES Brand (Brand_ID),
    CONSTRAINT fk_contenderships_fighter
        FOREIGN KEY (fighter_name) REFERENCES Fighter (Fighter_Name),
    CONSTRAINT fk_contenderships_season
        FOREIGN KEY (season_id) REFERENCES Season (Season_ID),
    CONSTRAINT fk_contenderships_scheduled_match
        FOREIGN KEY (earned_from_scheduled_match_id) REFERENCES scheduled_matches (scheduled_match_id),
    CONSTRAINT fk_contenderships_fight
        FOREIGN KEY (earned_from_fight_id) REFERENCES Fight (Fight_ID)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS fight_media (
    fight_media_id INT NOT NULL AUTO_INCREMENT,
    fight_id INT NULL,
    scheduled_match_id INT NULL,
    media_type ENUM('live', 'vod', 'clip', 'thumbnail', 'screenshot') NOT NULL,
    provider VARCHAR(32) NOT NULL,
    media_url VARCHAR(1024) NOT NULL,
    video_id VARCHAR(128) NULL,
    clip_id VARCHAR(128) NULL,
    start_offset_seconds INT NULL,
    end_offset_seconds INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (fight_media_id),
    KEY idx_fight_media_fight (fight_id),
    KEY idx_fight_media_scheduled_match (scheduled_match_id),
    CONSTRAINT fk_fight_media_fight
        FOREIGN KEY (fight_id) REFERENCES Fight (Fight_ID),
    CONSTRAINT fk_fight_media_scheduled_match
        FOREIGN KEY (scheduled_match_id) REFERENCES scheduled_matches (scheduled_match_id)
        ON DELETE SET NULL
) ENGINE=InnoDB;
