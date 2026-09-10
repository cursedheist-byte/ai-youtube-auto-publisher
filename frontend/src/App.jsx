import { Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Landing from "./pages/Landing";
import Setup from "./pages/Setup";
import AdminDashboard from "./pages/AdminDashboard";
import UserDashboard from "./pages/UserDashboard";
import DriveSources from "./pages/DriveSources";

function RoleHome() {
  const { user } = useAuth();
  return user?.role === "admin" ? <AdminDashboard /> : <UserDashboard />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/" element={<Landing />} />
      <Route path="/setup" element={<ProtectedRoute><Setup /></ProtectedRoute>} />
      <Route path="/app" element={<ProtectedRoute><RoleHome /></ProtectedRoute>} />
      <Route path="/drive-sources" element={<ProtectedRoute requireRole="admin"><DriveSources /></ProtectedRoute>} />
      <Route path="/dashboard" element={<ProtectedRoute><RoleHome /></ProtectedRoute>} />
    </Routes>
  );
}
