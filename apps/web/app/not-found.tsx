import { House } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyHeader, EmptyTitle } from "@/components/ui/empty";

export default function NotFound() {
  return (
    <Empty className="m-4 md:m-6">
      <EmptyHeader>
        <EmptyTitle>Page not found</EmptyTitle>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild variant="outline">
          <Link href="/">
            <House />
            Home
          </Link>
        </Button>
      </EmptyContent>
    </Empty>
  );
}
