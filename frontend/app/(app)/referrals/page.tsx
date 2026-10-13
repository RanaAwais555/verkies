"use client";

import { Handshake, Plus } from "lucide-react";
import { useState } from "react";

import { ReferralForm, ReferralTable } from "@/components/clients/referrals";
import { Button, Empty, ErrorNote, PageHeader, Panel, Skeleton } from "@/components/ui";
import { useApi, useCanChange } from "@/lib/hooks";
import type { Referral } from "@/lib/types";

export default function ReferralsPage() {
  const { data, error, mutate } = useApi<Referral[]>("/referrals");
  const [adding, setAdding] = useState(false);
  const writable = useCanChange();
  const converted = data?.filter((r) => r.converted).length ?? 0;
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Clients"
        title="Referrals"
        description="Who sends Verkies work. A referral converts when a deal on the referred company is won after it; revenue is those deals' values. To log one a client gave, use Referrals on their account."
        actions={
          writable &&
          !adding && (
            <Button variant="primary" onClick={() => setAdding(true)} icon={<Plus className="h-4 w-4" />}>
              Log a referral
            </Button>
          )
        }
      />
      {adding && (
        <ReferralForm
          onCancel={() => setAdding(false)}
          onDone={() => {
            setAdding(false);
            void mutate();
          }}
        />
      )}
      <Panel title="All referrals" description={data && data.length > 0 ? `${data.length} recorded, ${converted} converted.` : undefined}>
        {error ? (
          <ErrorNote error={error} />
        ) : !data ? (
          <Skeleton rows={4} />
        ) : data.length === 0 ? (
          <Empty icon={<Handshake className="h-4 w-4" />}>No referrals recorded yet.</Empty>
        ) : (
          <ReferralTable referrals={data} />
        )}
      </Panel>
    </div>
  );
}
