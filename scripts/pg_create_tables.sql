-- SQL to create required PostgreSQL tables for invoiceApp
-- Run this after running Django migrations on the Postgres DB (so auth_user exists)

BEGIN;

-- Business profiles table (primary key is user_id, referencing auth_user)
CREATE TABLE IF NOT EXISTS business_profiles (
    user_id BIGINT PRIMARY KEY REFERENCES auth_user(id) ON DELETE CASCADE,
    business_name TEXT,
    business_logo TEXT,
    business_address TEXT,
    street TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    country TEXT,
    email TEXT,
    phone TEXT,
    website TEXT,
    tax_id TEXT,
    created_date TIMESTAMP WITH TIME ZONE,
    last_login TIMESTAMP WITH TIME ZONE
);

-- Clients table
CREATE TABLE IF NOT EXISTS clients (
    client_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES auth_user(id) ON DELETE SET NULL,
    client_business_or_person_name TEXT,
    client_email TEXT,
    client_phone TEXT,
    client_address TEXT,
    created_date TIMESTAMP WITH TIME ZONE,
    total_invoices_sent INTEGER DEFAULT 0,
    total_amount_invoiced NUMERIC(14,2) DEFAULT 0.00
);

-- Invoices table
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES auth_user(id) ON DELETE CASCADE,
    client_id BIGINT REFERENCES clients(client_id) ON DELETE SET NULL,
    invoice_number TEXT UNIQUE,
    invoice_date DATE,
    due_date DATE,
    status TEXT,
    subtotal NUMERIC(14,2) DEFAULT 0.00,
    tax_rate NUMERIC(7,4) DEFAULT 0.0000,
    tax_amount NUMERIC(14,2) DEFAULT 0.00,
    discount_amount NUMERIC(14,2) DEFAULT 0.00,
    total_amount NUMERIC(14,2) DEFAULT 0.00,
    currency VARCHAR(8),
    payment_terms TEXT,
    notes TEXT,
    created_timestamp TIMESTAMP WITH TIME ZONE,
    last_modified_timestamp TIMESTAMP WITH TIME ZONE,
    pdf_generated BOOLEAN DEFAULT FALSE
);

-- Invoice items table
CREATE TABLE IF NOT EXISTS invoice_items (
    item_id BIGSERIAL PRIMARY KEY,
    invoice_id BIGINT REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    item_description TEXT,
    quantity NUMERIC(14,4) DEFAULT 1.0,
    unit_price NUMERIC(14,4) DEFAULT 0.00,
    line_total NUMERIC(18,4) DEFAULT 0.00,
    item_order INTEGER DEFAULT 0
);

-- User activity log
CREATE TABLE IF NOT EXISTS user_activity_logs (
    activity_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES auth_user(id) ON DELETE SET NULL,
    activity_type TEXT,
    timestamp TIMESTAMP WITH TIME ZONE,
    related_invoice_id BIGINT REFERENCES invoices(invoice_id)
);

-- Invoice templates
CREATE TABLE IF NOT EXISTS invoice_templates (
    template_id BIGSERIAL PRIMARY KEY,
    template_name TEXT,
    template_layout TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    created_date TIMESTAMP WITH TIME ZONE
);

-- Payment tracking
CREATE TABLE IF NOT EXISTS payment_tracking (
    payment_id BIGSERIAL PRIMARY KEY,
    invoice_id BIGINT REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    payment_status TEXT,
    payment_date TIMESTAMP WITH TIME ZONE,
    payment_method TEXT,
    amount_paid NUMERIC(14,2)
);

-- Email sending logs
CREATE TABLE IF NOT EXISTS email_sending_logs (
    email_log_id BIGSERIAL PRIMARY KEY,
    invoice_id BIGINT REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    recipient_email TEXT,
    email_type TEXT,
    status TEXT,
    sent_timestamp TIMESTAMP WITH TIME ZONE
);

-- Ad clicks table
CREATE TABLE IF NOT EXISTS ad_clicks (
    click_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES auth_user(id) ON DELETE SET NULL,
    session_id TEXT,
    ad_identifier TEXT,
    placement TEXT,
    timestamp TIMESTAMP WITH TIME ZONE,
    target_url TEXT,
    user_context TEXT,
    invoice_id BIGINT REFERENCES invoices(invoice_id)
);

COMMIT;
