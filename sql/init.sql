CREATE DATABASE IF NOT EXISTS learning_search
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE learning_search;

CREATE TABLE IF NOT EXISTS orders (
  id INT PRIMARY KEY,
  category VARCHAR(50),
  total_amount DECIMAL(10, 2)
);

INSERT IGNORE INTO orders (id, category, total_amount) VALUES
  (1, '数码', 100.00),
  (2, '数码', 200.00),
  (3, '服饰', 50.00);
