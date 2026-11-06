import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Layout from "./components/Layout.jsx";
import { ForgotPassword, Login, Register } from "./pages/Auth.jsx";
import Home from "./pages/Home.jsx";
import Risk from "./pages/Risk.jsx";
import Reports from "./pages/Reports.jsx";
import Chat from "./pages/Chat.jsx";
import Medicines from "./pages/Medicines.jsx";
import Appointments from "./pages/Appointments.jsx";
import Vitals from "./pages/Vitals.jsx";
import Emergency from "./pages/Emergency.jsx";
import Profile from "./pages/Profile.jsx";
import PublicCard from "./pages/PublicCard.jsx";
import Analytics from "./pages/Analytics.jsx";
import Wellness from "./pages/Wellness.jsx";
import Labs from "./pages/Labs.jsx";
import Hospitals from "./pages/Hospitals.jsx";
import Blood from "./pages/Blood.jsx";
import Prescribe from "./pages/Prescribe.jsx";
import ImageAI from "./pages/ImageAI.jsx";
import Messages from "./pages/Messages.jsx";
import Extras from "./pages/Extras.jsx";
import HospitalOps from "./pages/HospitalOps.jsx";
import Kiosk from "./pages/Kiosk.jsx";
import EarlyWarning from "./pages/EarlyWarning.jsx";
import Federated from "./pages/Federated.jsx";
import SecondOpinion from "./pages/SecondOpinion.jsx";
import Call from "./pages/Call.jsx";
import Wearables from "./pages/Wearables.jsx";
import RxScan from "./pages/RxScan.jsx";
import RxVerify from "./pages/RxVerify.jsx";
import RecordSecurity from "./pages/RecordSecurity.jsx";
import Contact, { ContactFab } from "./pages/Contact.jsx";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="p-8 text-center text-slate-500">Loading…</p>;
  return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <>
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot" element={<ForgotPassword />} />
      <Route path="/card/:token" element={<PublicCard />} />
      <Route path="/kiosk" element={<Kiosk />} />
      <Route path="/contact" element={<Contact />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<Home />} />
        <Route path="risk" element={<Risk />} />
        <Route path="reports" element={<Reports />} />
        <Route path="chat" element={<Chat />} />
        <Route path="medicines" element={<Medicines />} />
        <Route path="appointments" element={<Appointments />} />
        <Route path="vitals" element={<Vitals />} />
        <Route path="emergency" element={<Emergency />} />
        <Route path="profile" element={<Profile />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="wellness" element={<Wellness />} />
        <Route path="labs" element={<Labs />} />
        <Route path="hospitals" element={<Hospitals />} />
        <Route path="blood" element={<Blood />} />
        <Route path="prescribe" element={<Prescribe />} />
        <Route path="images" element={<ImageAI />} />
        <Route path="messages" element={<Messages />} />
        <Route path="extras" element={<Extras />} />
        <Route path="ops" element={<HospitalOps />} />
        <Route path="early-warning" element={<EarlyWarning />} />
        <Route path="federated" element={<Federated />} />
        <Route path="second-opinion" element={<SecondOpinion />} />
        <Route path="call/:aid" element={<Call />} />
        <Route path="wearables" element={<Wearables />} />
        <Route path="rx-scan" element={<RxScan />} />
        <Route path="rx-verify" element={<RxVerify />} />
        <Route path="security" element={<RecordSecurity />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    <ContactFab />
    </>
  );
}
