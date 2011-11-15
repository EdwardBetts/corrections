CREATE TABLE `changesets` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `created` datetime NOT NULL,
  `identifier` varchar(255) NOT NULL,
  `page` int(11) NOT NULL,
  PRIMARY KEY (`id`)
) DEFAULT CHARSET=utf8;

CREATE TABLE `edits` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `changeset` int(11) NOT NULL,
  `line` int(11) NOT NULL,
  `char_start` int(11) NOT NULL,
  `old_word` varchar(255) NOT NULL,
  `new_word` varchar(255) NOT NULL,
  `l` int(11) NOT NULL,
  `t` int(11) NOT NULL,
  `r` int(11) NOT NULL,
  `b` int(11) NOT NULL,
  PRIMARY KEY (`id`)
) DEFAULT CHARSET=utf8;

CREATE TABLE `items` (
  `identifier` varchar(255) NOT NULL,
  `leaf0_missing` tinyint(1) DEFAULT NULL,
  `abbyy_page_count` int(11) DEFAULT NULL,
  `abbyy_par_count` int(11) DEFAULT NULL,
  `abbyy_leaf_count` int(11) DEFAULT NULL,
  PRIMARY KEY (`identifier`)
) DEFAULT CHARSET=utf8;

CREATE TABLE `lines` (
  `identifier` varchar(255) NOT NULL,
  `page_num` int(11) NOT NULL,
  `line_num` int(11) NOT NULL,
  `good` tinyint(1) NOT NULL,
  PRIMARY KEY (`identifier`,`page_num`,`line_num`)
) DEFAULT CHARSET=utf8;

CREATE TABLE `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(255) NOT NULL,
  `site` char(2) NOT NULL,
  PRIMARY KEY (`id`)
) DEFAULT CHARSET=utf8;
