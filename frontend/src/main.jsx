import { createRoot } from "react-dom/client";

import App from "./App.jsx";

// Import order matters: tokens define the custom properties that base and
// components use, and animations is last so its reduced-motion overrides win.
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/animations.css";

createRoot(document.getElementById("root")).render(<App />);
