import { Link, useLocation } from "react-router-dom";
import { useEffect } from "react";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    if (import.meta.env.DEV) {
      console.error("404: non-existent route:", location.pathname);
    }
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="text-center space-y-4">
        <p className="text-7xl font-bold tabular-nums text-foreground">404</p>
        <p className="text-base text-muted-foreground">Page not found</p>
        <Link to="/" className="inline-block text-sm text-primary hover:underline">
          Return to dashboard
        </Link>
      </div>
    </div>
  );
};

export default NotFound;
