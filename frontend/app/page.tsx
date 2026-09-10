import { SectionTitle } from "@/components/common/SectionTitle";
import { QuickActions } from "@/components/home/QuickActions";
import { PageContainer } from "@/components/layout/PageContainer";
import { SystemStatusCard } from "@/components/system/SystemStatusCard";
import { APP_NAME } from "@/lib/env";
import { fetchReadiness } from "@/services/health";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const readiness = await fetchReadiness();

  return (
    <PageContainer>
      <div className="home-layout">
        <div className="home-layout__main">
          <section className="home-hero">
            <h1 className="home-hero__title">{APP_NAME}</h1>
            <p className="home-hero__desc">
              面向多行业团队的轻量级 AI 项目管理 Agent
            </p>
          </section>

          <SectionTitle flush>快捷入口</SectionTitle>
          <QuickActions />
        </div>

        <aside className="home-layout__aside">
          <SystemStatusCard readiness={readiness} />
        </aside>
      </div>
    </PageContainer>
  );
}
