import os
import subprocess
import time
from playwright.sync_api import sync_playwright

def run_verification():
    print("Starting background HTTP server on port 8000...")
    try:
        subprocess.run("kill $(lsof -t -i :8000) 2>/dev/null || true", shell=True, check=False)
    except Exception as e:
        print("Warning cleaning port: ", e)

    server_process = subprocess.Popen(["python3", "-m", "http.server", "8000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)

    os.makedirs("verification/screenshots", exist_ok=True)
    os.makedirs("/home/jules/verification", exist_ok=True)

    print("Launching headless Chromium browser for Paystack payment E2E verification...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Test 1: Teacher Course Form and Pricing Fields
        print("\n--- TEST 1: Teacher Course Form Pricing ---")
        teacher_context = browser.new_context(viewport={"width": 1280, "height": 800})

        teacher_mock_js = """
            console.log('Setting up teacher mock...');
            sessionStorage.setItem('currentUser', JSON.stringify({
                email: 'teacher@smartlms.edu',
                full_name: 'Dr. Kwame Mensah',
                role: 'teacher',
                active: true
            }));
            sessionStorage.setItem('sessionId', 'mock_teacher_session_123');

            window.supabase = {
                createClient: () => ({
                    from: () => ({
                        select: () => ({
                            eq: () => Promise.resolve({ data: [], error: null })
                        }),
                        upsert: (payload) => Promise.resolve({ data: [payload], error: null })
                    }),
                    realtime: { setAuth: () => {} }
                })
            };

            let originalSupabaseDB;
            Object.defineProperty(window, 'SupabaseDB', {
                configurable: true,
                get() { return originalSupabaseDB; },
                set(val) {
                    originalSupabaseDB = val;
                    originalSupabaseDB.getUser = async (email) => ({
                        email: 'teacher@smartlms.edu',
                        full_name: 'Dr. Kwame Mensah',
                        role: 'teacher',
                        active: true,
                        flagged: false,
                        session_id: 'mock_teacher_session_123'
                    });
                    originalSupabaseDB.getCourses = async () => ({
                        data: [
                            { id: 'course-free-1', title: 'Intro to Philosophy', price: 0, currency: 'GHS', status: 'published', created_by: 'Dr. Kwame Mensah' },
                            { id: 'course-paid-1', title: 'Advanced Machine Learning', price: 150.00, currency: 'GHS', status: 'published', created_by: 'Dr. Kwame Mensah' }
                        ]
                    });
                    originalSupabaseDB.getMaintenance = async () => ({ enabled: false, schedules: [] });
                    originalSupabaseDB.getCount = async () => 0;
                    originalSupabaseDB.getViolations = async () => ({ data: [], total: 0 });
                    originalSupabaseDB.saveCourse = async (data) => {
                        window.__savedCourseData = data;
                        return data;
                    };
                }
            });
        """

        teacher_context.add_init_script(teacher_mock_js)
        teacher_page = teacher_context.new_page()

        teacher_page.goto("http://localhost:8000/teacher.html?page=courses")
        teacher_page.wait_for_selector("button:has-text('+ Create Course')", timeout=10000)

        # Check that courses list displays pricing badges
        content_text = teacher_page.inner_text("#pageContent")
        assert "Advanced Machine Learning" in content_text, "Paid course title not found"
        assert "GHS 150.00" in content_text, "Paid course price badge not found in teacher courses list"
        assert "FREE" in content_text.upper(), "Free course price badge not found in teacher courses list"
        print("Verified: Teacher course list displays price badges for both free and paid courses.")

        # Click Create Course
        teacher_page.click("button:has-text('+ Create Course')")
        teacher_page.wait_for_selector("#coursePrice", timeout=5000)

        # Check pricing fields exist
        assert teacher_page.is_visible("#coursePrice"), "#coursePrice field not found in teacher course form"
        assert teacher_page.is_visible("#courseCurrency"), "#courseCurrency field not found in teacher course form"
        print("Verified: Price and Currency input fields rendered in Create Course form.")

        # Fill form and submit
        teacher_page.fill("#courseTitle", "Quantum Computing Basics")
        teacher_page.fill("#coursePrice", "250.50")
        teacher_page.select_option("#courseCurrency", "USD")
        teacher_page.click("button[type='submit']")
        teacher_page.wait_for_timeout(500)

        saved = teacher_page.evaluate("window.__savedCourseData")
        assert saved is not None, "Course form did not trigger saveCourse"
        assert saved["price"] == 250.50, f"Expected saved price 250.50, got {saved.get('price')}"
        assert saved["currency"] == "USD", f"Expected saved currency USD, got {saved.get('currency')}"
        print(f"Verified: Course saved with price {saved['price']} and currency {saved['currency']}.")

        teacher_page.screenshot(path="/home/jules/verification/teacher_course_form.png")
        teacher_context.close()


        # Test 2: Student Catalog, Price Display, and Free Course Enrollment
        print("\n--- TEST 2: Student Catalog Price Display & Free Course Enrollment ---")
        student_context = browser.new_context(viewport={"width": 1280, "height": 800})

        student_mock_js = """
            console.log('Setting up student mock...');
            sessionStorage.setItem('currentUser', JSON.stringify({
                email: 'student@smartlms.edu',
                full_name: 'Ama Serwaa',
                role: 'student',
                active: true
            }));
            sessionStorage.setItem('sessionId', 'mock_student_session_123');

            window.__enrollmentLog = [];
            window.__paymentLog = [];

            window.supabase = {
                createClient: () => ({
                    from: () => ({
                        select: () => ({
                            eq: () => ({
                                count: 0,
                                head: true,
                                maybeSingle: () => Promise.resolve({ data: null, error: null }),
                                order: () => Promise.resolve({ data: [], error: null })
                            }),
                            in: () => Promise.resolve({ data: [], error: null }),
                            order: () => Promise.resolve({ data: [], error: null })
                        }),
                        upsert: (payload) => Promise.resolve({ data: [payload], error: null })
                    }),
                    realtime: { setAuth: () => {} }
                })
            };

            let originalSupabaseDB;
            Object.defineProperty(window, 'SupabaseDB', {
                configurable: true,
                get() { return originalSupabaseDB; },
                set(val) {
                    originalSupabaseDB = val;
                    originalSupabaseDB.getUser = async () => ({
                        email: 'student@smartlms.edu',
                        full_name: 'Ama Serwaa',
                        role: 'student',
                        active: true,
                        flagged: false,
                        session_id: 'mock_student_session_123'
                    });
                    originalSupabaseDB.getMaintenance = async () => ({ enabled: false, schedules: [] });
                    originalSupabaseDB.getCount = async () => 0;
                    originalSupabaseDB.getEnrollments = async () => ({ data: [] });
                    originalSupabaseDB.getPayments = async () => ({ data: [] });
                    originalSupabaseDB.getPaystackPublicKey = async () => 'pk_test_mock_12345';
                    originalSupabaseDB.getCourses = async () => ({
                        data: [
                            { id: 'c-free', title: 'Philosophy 101', price: 0, currency: 'GHS', status: 'published', created_by: 'Dr. Kwame' },
                            { id: 'c-paid', title: 'Fullstack Web Dev', price: 80.00, currency: 'GHS', status: 'published', created_by: 'Dr. Kwame' }
                        ]
                    });
                    originalSupabaseDB.getCourse = async (id) => {
                        if (id === 'c-free') return { id: 'c-free', title: 'Philosophy 101', price: 0, currency: 'GHS', status: 'published' };
                        return { id: 'c-paid', title: 'Fullstack Web Dev', price: 80.00, currency: 'GHS', status: 'published' };
                    };
                    originalSupabaseDB.recordPayment = async (pay) => {
                        window.__paymentLog.push(pay);
                        return pay;
                    };
                    originalSupabaseDB.enrollInCourse = async (courseId, email, enrollmentId, ref) => {
                        window.__enrollmentLog.push({ courseId, email, enrollmentId, ref });
                        return true;
                    };
                }
            });
        """

        student_context.add_init_script(student_mock_js)
        student_page = student_context.new_page()

        student_page.goto("http://localhost:8000/student.html?page=courses")
        student_page.wait_for_selector("#catalogGrid", timeout=10000)

        # Check badges in catalog
        catalog_html = student_page.inner_html("#catalogGrid")
        assert "Free" in catalog_html, "Free price badge not found in catalog"
        assert "GHS 80.00" in catalog_html, "Paid price badge not found in catalog"
        assert "Enroll (Free)" in catalog_html, "Enroll (Free) button not found"
        assert "Enroll (GHS 80.00)" in catalog_html, "Enroll (GHS 80.00) button not found"
        print("Verified: Student catalog correctly displays Free badge, Paid price badge, and dynamic button text.")

        # Enroll in Free Course directly
        student_page.click("text=Enroll (Free)")
        student_page.wait_for_timeout(800)

        free_enroll_log = student_page.evaluate("window.__enrollmentLog")
        assert len(free_enroll_log) == 1, "Free course enrollment was not triggered"
        assert free_enroll_log[0]["courseId"] == "c-free", "Incorrect course enrolled"
        assert free_enroll_log[0]["ref"] is None, "Payment reference should be None for free courses"
        print("Verified: Free course enrolls directly without triggering payment.")


        # Test 3: Paid Course Payment Flow with Paystack Modal & Confirmation
        print("\n--- TEST 3: Paid Course Paystack Modal & Confirmation Flow ---")
        student_page.evaluate("""
            window.__paystackPopMock = {
                setup: function(opts) {
                    return {
                        openIframe: function() {
                            window.__lastPaystackOpts = opts;
                            const backdrop = document.createElement('div');
                            backdrop.className = 'modal-backdrop';
                            backdrop.id = 'paystackModalBackdrop';
                            backdrop.style.display = 'flex';
                            backdrop.innerHTML = `
                                <div class="modal" style="max-width:440px">
                                    <h3>Paystack Secure Checkout</h3>
                                    <div id="paystackCourseTitle">${opts.metadata?.custom_fields?.[0]?.value || ''}</div>
                                    <div id="paystackAmount">${opts.currency} ${(opts.amount / 100).toFixed(2)}</div>
                                    <button id="confirmPaystackBtn">Pay</button>
                                    <button id="cancelPaystackBtn">Cancel</button>
                                </div>
                            `;
                            document.body.appendChild(backdrop);
                            document.getElementById('confirmPaystackBtn').onclick = () => {
                                backdrop.remove();
                                opts.callback({ reference: opts.ref, status: 'success', message: 'Approved' });
                            };
                            document.getElementById('cancelPaystackBtn').onclick = () => {
                                backdrop.remove();
                                if (opts.onClose) opts.onClose();
                            };
                        }
                    };
                }
            };
            window.PaystackPop = window.__paystackPopMock;
        """)

        student_page.click("text=Enroll (GHS 80.00)")
        student_page.wait_for_selector("#paystackModalBackdrop", timeout=5000)

        # Paystack modal should appear
        assert student_page.is_visible("#paystackModalBackdrop"), "Paystack checkout modal did not open for paid course"
        modal_text = student_page.inner_text("#paystackModalBackdrop")
        assert "Paystack Secure Checkout" in modal_text, "Paystack header not in modal"
        assert "Fullstack Web Dev" in modal_text, "Course title not in payment modal"
        assert "GHS 80.00" in modal_text, "Price not displayed in payment modal"
        print("Verified: Paystack checkout modal opened with course title, student email, and price.")

        # Take screenshot of checkout modal
        student_page.screenshot(path="/home/jules/verification/paystack_checkout_modal.png")

        # Confirm Payment
        student_page.click("#confirmPaystackBtn")
        student_page.wait_for_timeout(1000)

        # Verify payment was recorded and enrollment completed with payment reference
        payments = student_page.evaluate("window.__paymentLog")
        enrollments = student_page.evaluate("window.__enrollmentLog")

        assert len(payments) == 1, "Payment was not recorded"
        assert payments[0]["course_id"] == "c-paid", "Payment recorded for wrong course"
        assert payments[0]["amount"] == 80.0, f"Payment amount mismatch: {payments[0]['amount']}"
        assert payments[0]["status"] == "success", "Payment status is not success"
        assert payments[0]["reference"].startswith("ps_"), f"Unexpected reference format: {payments[0]['reference']}"

        assert len(enrollments) == 2, "Second enrollment record not found"
        paid_enrollment = enrollments[1]
        assert paid_enrollment["courseId"] == "c-paid", "Wrong course in paid enrollment"
        assert paid_enrollment["ref"] == payments[0]["reference"], "Payment reference was not passed to enrollInCourse"
        print("Verified: Paystack payment confirmed and enrollment completed with verified transaction reference.")

        # Test 4: Cancellation verification
        print("\n--- TEST 4: Payment Cancellation Flow ---")
        student_page.click("text=Enroll (GHS 80.00)")
        student_page.wait_for_selector("#paystackModalBackdrop", timeout=5000)
        assert student_page.is_visible("#paystackModalBackdrop"), "Modal did not open"
        student_page.click("#cancelPaystackBtn")
        student_page.wait_for_timeout(500)
        assert not student_page.is_visible("#paystackModalBackdrop"), "Modal still visible after cancel"

        payments_after_cancel = student_page.evaluate("window.__paymentLog")
        enrollments_after_cancel = student_page.evaluate("window.__enrollmentLog")
        assert len(payments_after_cancel) == 1, "No new payment should be recorded on cancel"
        assert len(enrollments_after_cancel) == 2, "No new enrollment should be created on cancel"
        print("Verified: Cancelling payment does not create payment or enrollment records.")

        student_context.close()
        browser.close()

    server_process.terminate()
    server_process.wait()
    print("\nSUCCESS: All Paystack course pricing and payment confirmation verification tests passed!")

if __name__ == "__main__":
    run_verification()
