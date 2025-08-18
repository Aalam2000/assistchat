--
-- PostgreSQL database dump
--

-- Dumped from database version 16.9 (Debian 16.9-1.pgdg130+1)
-- Dumped by pg_dump version 16.9 (Debian 16.9-1.pgdg130+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: tg_accounts; Type: TABLE DATA; Schema: public; Owner: assistuser
--

INSERT INTO public.tg_accounts (id, label, phone_e164, tg_user_id, username, app_id, app_hash, string_session, status, reply_policy, twofa_enabled, last_login_at, last_seen_at, session_updated_at, created_at, updated_at) VALUES ('090e36bf-9da6-4068-9e60-41070f128063', 'Main account', '+994513935351', 8167687813, 'bluesmash', 28298030, 'edb3a353bed820ca324cad6e3177fa95', '1ApWapzMBu6UqNzNvD46nlSHWUR_zkQrCVX41srr89MtGq1h4FG_ZNxmV3brqKVKQD2cLU5qlktC002pWkZYhhzggLxLGPOf_lngbXCVDvntvdM6SOB65c605ZzEcw_5A3qOuY1Ckhe1sI1xNbgpN12jhpXE-p7b0HaaS7uXT1lxRPr1FAuJ89WWYqqMQdOQQfULF4sSgyi9jcIr_4SZROP1r_qIA7ss4hapkLXKR6i5QjcvGHoYNk81W6g3ai8YzCEUeDzP6w-_bgSUnEhUbgwT0-nLgICYRcWGX8Dx4qWrX6cF05vKofBgkR4rkQ08riU-qlIHniNFTRFsMamK-XUn_0yM88q4=', 'active', 'dm_only', false, '2025-08-17 12:05:29.443926+00', '2025-08-17 11:55:03.673704+00', '2025-08-17 12:05:29.443926+00', '2025-08-17 11:55:03.673704+00', '2025-08-17 12:05:29.443926+00');


--
-- PostgreSQL database dump complete
--

