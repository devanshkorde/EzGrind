-- MySQL dump 10.13  Distrib 8.0.44, for Win64 (x86_64)
--
-- Host: localhost    Database: ezgrind_db
-- ------------------------------------------------------
-- Server version	8.0.44

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `exercises`
--

DROP TABLE IF EXISTS `exercises`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `exercises` (
  `exercise_id` int NOT NULL AUTO_INCREMENT,
  `exercise_name` varchar(100) NOT NULL,
  `muscle_id` int NOT NULL,
  `equipment` varchar(50) DEFAULT NULL,
  `description` text,
  PRIMARY KEY (`exercise_id`),
  KEY `muscle_id` (`muscle_id`),
  CONSTRAINT `exercises_ibfk_1` FOREIGN KEY (`muscle_id`) REFERENCES `muscle_groups` (`muscle_id`)
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `exercises`
--

LOCK TABLES `exercises` WRITE;
/*!40000 ALTER TABLE `exercises` DISABLE KEYS */;
INSERT INTO `exercises` VALUES (1,'Bench Press',1,'Barbell','Primary chest pressing movement'),(2,'Incline Dumbbell Press',1,'Dumbbell','Upper chest focused press'),(3,'Lat Pulldown',2,'Machine','Vertical pulling for lats'),(4,'Pull Ups',2,'Bodyweight','Bodyweight lat exercise'),(5,'Seated Cable Row',3,'Cable','Upper back rowing movement'),(6,'Face Pulls',3,'Cable','Rear delts and upper back'),(7,'Deadlift',4,'Barbell','Posterior chain and lower back'),(8,'Back Extensions',4,'Machine','Lower back isolation'),(9,'Bicep Curl',5,'Dumbbell','Biceps isolation'),(10,'Hammer Curl',5,'Dumbbell','Biceps brachialis focus'),(11,'Tricep Pushdown',6,'Cable','Triceps isolation'),(12,'Skull Crushers',6,'Barbell','Overhead triceps movement'),(13,'Squat',7,'Barbell','Compound quad movement'),(14,'Leg Press',7,'Machine','Quad dominant leg press'),(15,'Romanian Deadlift',8,'Barbell','Hamstring hinge movement'),(16,'Leg Curl',8,'Machine','Hamstring isolation'),(17,'Hip Thrust',9,'Barbell','Primary glute builder'),(18,'Glute Bridge',9,'Bodyweight','Glute activation'),(19,'Standing Calf Raise',10,'Machine','Calf isolation'),(20,'Seated Calf Raise',10,'Machine','Soleus focused calf work'),(21,'Overhead Press',11,'Barbell','Shoulder press'),(22,'Lateral Raises',11,'Dumbbell','Side delts isolation'),(23,'Plank',12,'Bodyweight','Core stability exercise'),(24,'Hanging Leg Raises',12,'Bodyweight','Lower abdominal focus');
/*!40000 ALTER TABLE `exercises` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `muscle_groups`
--

DROP TABLE IF EXISTS `muscle_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `muscle_groups` (
  `muscle_id` int NOT NULL AUTO_INCREMENT,
  `muscle_name` varchar(50) NOT NULL,
  `image_path` varchar(255) NOT NULL,
  PRIMARY KEY (`muscle_id`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `muscle_groups`
--

LOCK TABLES `muscle_groups` WRITE;
/*!40000 ALTER TABLE `muscle_groups` DISABLE KEYS */;
INSERT INTO `muscle_groups` VALUES (1,'Chest','assets/muscles/chest.png'),(2,'Lats','assets/muscles/lats.png'),(3,'Upper Back','assets/muscles/upper_back.png'),(4,'Lower Back','assets/muscles/lower_back.png'),(5,'Biceps','assets/muscles/biceps.png'),(6,'Triceps','assets/muscles/triceps.png'),(7,'Quads','assets/muscles/quads.png'),(8,'Hamstrings','assets/muscles/hamstrings.png'),(9,'Glutes','assets/muscles/glutes.png'),(10,'Calves','assets/muscles/calves.png'),(11,'Shoulders','assets/muscles/shoulders.png'),(12,'Core','assets/muscles/core.png');
/*!40000 ALTER TABLE `muscle_groups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `user_id` int NOT NULL AUTO_INCREMENT,
  `full_name` varchar(100) NOT NULL,
  `email` varchar(100) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `contact_number` varchar(15) DEFAULT NULL,
  `date_of_birth` date DEFAULT NULL,
  `height_cm` float DEFAULT NULL,
  `weight_kg` float DEFAULT NULL,
  `fitness_goal` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'Devansh Test','devansh@ezgrind.com','hashed_password_demo','2026-02-02 18:04:22',NULL,NULL,NULL,NULL,NULL),(2,'Devansh Korde','devanshkorde195@gmail.com','scrypt:32768:8:1$Cr595sxY0kHcjUKc$9f6490eba1cb8ce9f0a7e050fda7088a3e784dfede99044a51bd5942dfef9b11ce2b3b635ada550c5f0cff3ab34ce44a9a9fd892dac81f454ba7b8d277855522','2026-02-03 14:07:48',NULL,NULL,NULL,NULL,NULL),(3,'Arnav Jaiswal','arnavj18@gmail.com','scrypt:32768:8:1$WmfH1UTrHptweZcB$ddea6f229d21fc97896c776c1a338f4687708a06cc29eacbc938b5bbe108abec2b7ff83192f76cc6f81b080898931c249b228fd702e497eb4c23b32de0b077c9','2026-02-17 13:34:22','6388631609','2005-01-18',178,80,'lose'),(4,'Siddharth Jain','sid29@gmail.com','scrypt:32768:8:1$u3HAuYlB8e1las0p$1ad08e6033876b9f0bb887aaa951b1f0ea4315f8170d378f1d2394aea792e0713d6f2d5efa6e9626aa856833f34650d12069afc44931b77ece52ceed02d1d54c','2026-02-17 17:07:21','8989034399','2005-03-29',180,85,'lose'),(5,'Aviral Patil','aviral@gmail.com','scrypt:32768:8:1$sgC6TBpLg3ek6FoW$a1547547f5844d600915859d07bddab20686edf5d5894486ed2021f89fe3a16ec7492443b0851ccb074f514063562ede942ac942aba7d02334fa7ffdc78f1b16','2026-02-18 10:01:46','7896541236','2013-10-14',175,65,'muscle'),(6,'123','77@gmail.com','scrypt:32768:8:1$H2bHC9VJlVhFSGvj$0754f0f634a6434992b93eae6fa53bb1dfbe4b0088caefe05bcaa1e3a233fb7d05009b0ec77a1aa948cba4f2a721cbbe7c9ec4edaa06e13b9df5ce38746c8038','2026-02-19 06:53:26','kjh','2026-02-21',789,789,''),(7,'tanveer','tanveer@gmail.com','scrypt:32768:8:1$6tjUfQuNU4WjgvQq$833c5919c7e7b3c57690f237edefffe24e4e7a87627f12e57b6a1a5f65a3e876ade5226cd7cac95ca279553e9b5a9a34d4df7df49dc3bd29930bc6dbd8dc792d','2026-03-30 09:57:26','7896541278','2005-06-05',178,100,'lose'),(8,'Devansh Korde','devanshkorde@gmail.com','scrypt:32768:8:1$YN9PnXS7rUr7To2N$fcfbc5efaa8bf915676bdb4891f25a21d7b1f6bfef29d8306ce18207f39ad36ca4ddd7916ebd29ad9c5544432fd74de281cead5b6b4b50fec527f7ea513dae8f','2026-05-08 10:00:47','9754111000','2026-05-20',188,90,'lose'),(10,'Arnav','arnav@bhosda.com','scrypt:32768:8:1$m9X75eF5pSsGDVt8$799eae60b64d0e63b6a40cbfb91f0ed8d1b32f2de181644b96a4488770a9b605e85dddc1e71f68af2440c2b0fbc06c524978f2b0af6cf619e80371d4f69d733f','2026-07-22 17:28:47','9874585655','2005-01-18',175,85,'lose'),(12,'Test User','testuser1023306553@example.com','scrypt:32768:8:1$N9qMIwRCEE8FAluF$44a4db7b64a30aec13b7167f59f6f151f4a4d617a653c99089d9e5748a8b17247d18717e3e50a1a8d0551022c6f35ef1d2d0cb996f38b065b8a7f388ed85ac7c','2026-07-23 12:16:14','9876543210','2000-01-15',175,70,'muscle'),(13,'Login Test','logintest1757153500@example.com','scrypt:32768:8:1$DLaTzJyMMAHo3JL1$f58a45d32dbbb2d8f3bc39c1e47b276a21b08d2ea056b33acaa1cb433afb8cbc64300a1686c5a4b169605e4eb885446bd285fec3a810aa1527584788f7aba553','2026-07-23 12:16:27',NULL,NULL,NULL,NULL,'muscle'),(14,'Siddharth','sid@gmail.com','scrypt:32768:8:1$OPXvU3KJnBCSqe3B$c7c0e2ae5fa0bf885f87ad259f248802883b0185c260563addf315b5ba519fcc961a760cdd2143d4bc5bb1e8a4a022f4d84fb3fc1adbef89abd0fb78b5fc590b','2026-07-28 09:52:11','9745623586','2006-02-06',175,85,'lose'),(15,'Smoke Test','smoke+1785233925@ezgrind.test','scrypt:32768:8:1$czzsevzRS8AVEQ2o$8fc23b7de5e77abbeb7695fff25588ee6910af314172007cbd069edf6b8aadfc19e8af8c7dfa2d52c020ea66f9620623897aa055c8bcb307fc3b046049877263','2026-07-28 10:18:45','9999999999','1990-01-01',180,75,'muscle');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `workout_sets`
--

DROP TABLE IF EXISTS `workout_sets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `workout_sets` (
  `set_id` int NOT NULL AUTO_INCREMENT,
  `workout_id` int NOT NULL,
  `exercise_id` int NOT NULL,
  `weight` decimal(5,2) DEFAULT NULL,
  `reps` int DEFAULT NULL,
  `time_under_tension` int DEFAULT NULL,
  PRIMARY KEY (`set_id`),
  KEY `workout_id` (`workout_id`),
  KEY `exercise_id` (`exercise_id`),
  CONSTRAINT `workout_sets_ibfk_1` FOREIGN KEY (`workout_id`) REFERENCES `workouts` (`workout_id`),
  CONSTRAINT `workout_sets_ibfk_2` FOREIGN KEY (`exercise_id`) REFERENCES `exercises` (`exercise_id`)
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `workout_sets`
--

LOCK TABLES `workout_sets` WRITE;
/*!40000 ALTER TABLE `workout_sets` DISABLE KEYS */;
INSERT INTO `workout_sets` VALUES (1,1,1,60.00,10,40),(2,1,1,65.00,8,35),(3,1,3,70.00,10,45),(4,1,5,60.00,12,40),(5,1,9,12.00,12,30),(6,1,11,25.00,10,30),(7,2,3,40.00,15,75),(8,3,1,50.00,12,60),(9,4,17,120.00,15,60),(10,5,9,10.00,15,60),(11,6,2,25.00,12,45),(12,6,3,50.00,12,60),(13,7,3,40.00,15,60),(14,8,1,15.00,15,60),(15,8,1,20.00,12,45),(16,7,1,15.00,15,60),(17,7,1,20.00,12,45),(18,9,5,50.00,15,60),(19,9,9,10.00,15,30),(21,11,13,60.00,15,60),(22,11,13,70.00,12,45),(23,12,8,60.00,8,NULL);
/*!40000 ALTER TABLE `workout_sets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `workouts`
--

DROP TABLE IF EXISTS `workouts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `workouts` (
  `workout_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `workout_date` date NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`workout_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `workouts_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `workouts`
--

LOCK TABLES `workouts` WRITE;
/*!40000 ALTER TABLE `workouts` DISABLE KEYS */;
INSERT INTO `workouts` VALUES (1,1,'2026-02-02','2026-02-02 18:04:38'),(2,1,'2026-02-03','2026-02-03 13:45:41'),(3,1,'2026-02-04','2026-02-04 06:48:39'),(4,1,'2026-02-05','2026-02-05 05:43:01'),(5,2,'2026-02-16','2026-02-16 14:23:40'),(6,2,'2026-02-17','2026-02-17 12:55:09'),(7,4,'2026-02-18','2026-02-18 07:57:30'),(8,2,'2026-02-18','2026-02-18 17:02:44'),(9,2,'2026-02-19','2026-02-19 06:12:31'),(11,10,'2026-07-23','2026-07-23 12:30:14'),(12,15,'2026-07-28','2026-07-28 10:18:45');
/*!40000 ALTER TABLE `workouts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping events for database 'ezgrind_db'
--

--
-- Dumping routines for database 'ezgrind_db'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-07-29 11:16:58
