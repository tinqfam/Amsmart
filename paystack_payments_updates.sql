-- ============================================================================
-- Migration: Paystack Course Pricing & Payment Integration
-- ============================================================================

-- 1. COURSES TABLE UPDATES: Add pricing support
ALTER TABLE courses ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2) DEFAULT 0.00;
ALTER TABLE courses ADD COLUMN IF NOT EXISTS currency VARCHAR(10) DEFAULT 'GHS';

-- Ensure non-negative price constraint
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'courses_price_non_negative'
  ) THEN
    ALTER TABLE courses ADD CONSTRAINT courses_price_non_negative CHECK (price >= 0);
  END IF;
END $$;

-- 2. PAYMENTS TABLE: Record Paystack transactions
CREATE TABLE IF NOT EXISTS payments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
  student_email VARCHAR(255) REFERENCES users(email) ON UPDATE CASCADE ON DELETE CASCADE CHECK (student_email = LOWER(student_email)),
  amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
  currency VARCHAR(10) NOT NULL DEFAULT 'GHS',
  reference VARCHAR(255) UNIQUE NOT NULL,
  status VARCHAR(50) NOT NULL DEFAULT 'success' CHECK (status IN ('pending', 'success', 'failed')),
  paystack_response JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_payments_student_email ON payments(student_email);
CREATE INDEX IF NOT EXISTS idx_payments_course_id ON payments(course_id);
CREATE INDEX IF NOT EXISTS idx_payments_reference ON payments(reference);
CREATE INDEX IF NOT EXISTS idx_payments_course_student ON payments(course_id, student_email);

-- 3. ROW LEVEL SECURITY ON PAYMENTS TABLE
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Payments: Student Access" ON payments;
CREATE POLICY "Payments: Student Access" ON payments FOR SELECT USING (
  student_email = get_auth_email() OR
  is_admin() OR
  (is_teacher() AND EXISTS (SELECT 1 FROM courses WHERE id = payments.course_id AND teacher_email = get_auth_email()))
);

DROP POLICY IF EXISTS "Payments: Student Insert" ON payments;
CREATE POLICY "Payments: Student Insert" ON payments FOR INSERT WITH CHECK (
  student_email = get_auth_email() OR is_admin()
);

DROP POLICY IF EXISTS "Payments: Admin All" ON payments;
CREATE POLICY "Payments: Admin All" ON payments FOR ALL USING (is_admin());

-- 4. ENROLLMENT RPC WITH PAYMENT CONFIRMATION ENFORCEMENT
-- Updates enroll_in_course to support optional payment reference and enforce paid course rules
CREATE OR REPLACE FUNCTION enroll_in_course(
  p_course_id UUID,
  p_student_email VARCHAR,
  p_enrollment_id VARCHAR DEFAULT NULL,
  p_payment_reference VARCHAR DEFAULT NULL
)
RETURNS VOID AS $$
DECLARE
  v_actual_enrollment_id VARCHAR;
  v_course_status VARCHAR;
  v_enrollment_limit INTEGER;
  v_current_enrollments INTEGER;
  v_course_price NUMERIC(10, 2);
  v_currency VARCHAR(10);
  v_has_confirmed_payment BOOLEAN;
BEGIN
  -- Normalize student email to lower case
  p_student_email := LOWER(TRIM(p_student_email));

  SELECT enrollment_id, status, enrollment_limit, COALESCE(price, 0.00), COALESCE(currency, 'GHS')
  INTO v_actual_enrollment_id, v_course_status, v_enrollment_limit, v_course_price, v_currency
  FROM courses WHERE id = p_course_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Course not found.';
  END IF;

  -- 1. Idempotency Check: If already enrolled, success (do nothing)
  IF EXISTS (SELECT 1 FROM enrollments WHERE course_id = p_course_id AND student_email = p_student_email) THEN
    RETURN;
  END IF;

  IF v_course_status != 'published' THEN
    RAISE EXCEPTION 'Cannot enroll in a course that is not published.';
  END IF;

  -- 2. Payment Verification for Paid Courses
  IF v_course_price > 0 THEN
    -- Check if student has a confirmed payment record for this course
    IF p_payment_reference IS NOT NULL AND p_payment_reference != '' THEN
      SELECT EXISTS (
        SELECT 1 FROM payments
        WHERE course_id = p_course_id
          AND student_email = p_student_email
          AND reference = p_payment_reference
          AND status = 'success'
      ) INTO v_has_confirmed_payment;
    ELSE
      SELECT EXISTS (
        SELECT 1 FROM payments
        WHERE course_id = p_course_id
          AND student_email = p_student_email
          AND status = 'success'
      ) INTO v_has_confirmed_payment;
    END IF;

    IF NOT v_has_confirmed_payment THEN
      RAISE EXCEPTION 'Payment Required: This course costs % % and requires confirmed payment before enrollment.', v_currency, v_course_price;
    END IF;
  END IF;

  -- 3. Enrollment ID Check (Optional teacher password)
  IF v_actual_enrollment_id IS NOT NULL AND (p_enrollment_id IS NULL OR v_actual_enrollment_id != p_enrollment_id) THEN
    RAISE EXCEPTION 'Invalid Enrollment ID';
  END IF;

  -- 4. Capacity Limit Check
  IF v_enrollment_limit IS NOT NULL AND v_enrollment_limit > 0 THEN
    SELECT COUNT(*)::INTEGER INTO v_current_enrollments FROM enrollments WHERE course_id = p_course_id;
    IF v_current_enrollments >= v_enrollment_limit THEN
      RAISE EXCEPTION 'Course Full: The enrollment limit for this course has been reached.';
    END IF;
  END IF;

  -- 5. Insert Enrollment Record
  INSERT INTO enrollments (course_id, student_email)
  VALUES (p_course_id, p_student_email)
  ON CONFLICT (course_id, student_email) DO NOTHING;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
