package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapConflictException;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapResult;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberLimitExceededException;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdMembershipService;
import io.github.xxh3898.ourledger.household.HouseholdMembershipConflictException;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class HouseholdDomainIntegrationTest {

    private static final HouseholdBootstrapRequest BOOTSTRAP_REQUEST =
            new HouseholdBootstrapRequest(
                    "테스트 Household",
                    "owner@example.test",
                    "Owner",
                    "member@example.test",
                    "Member"
            );

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private HouseholdRepository householdRepository;

    @Autowired
    private HouseholdMemberRepository householdMemberRepository;

    @Autowired
    private HouseholdMembershipService householdMembershipService;

    @Autowired
    private HouseholdBootstrapService householdBootstrapService;

    @Autowired
    private ApplicationContext applicationContext;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void clearDatabase() {
        householdMemberRepository.deleteAllInBatch();
        householdRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
    }

    @Test
    void should_normalizeEmailAndRejectCaseDuplicate_when_usersArePersisted() {
        User first = userRepository.saveAndFlush(User.create(" Owner@Example.Test ", "Owner"));

        assertThat(first.getEmail()).isEqualTo("owner@example.test");
        assertThatThrownBy(() ->
                userRepository.saveAndFlush(User.create("OWNER@EXAMPLE.TEST", "Duplicate")))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void should_createAuthHouseholdColumnsWithoutCredentials_when_v2MigrationIsApplied() {
        assertThat(jdbcTemplate.queryForList(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('users', 'households', 'household_members')
                ORDER BY table_name
                """,
                String.class
        )).containsExactly("household_members", "households", "users");

        assertThat(jdbcTemplate.queryForList(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'users'
                ORDER BY ordinal_position
                """,
                String.class
        )).containsExactly("id", "email", "display_name", "status", "created_at", "updated_at")
                .doesNotContain("password_hash");
    }

    @Test
    void should_applyKrwAndSeoulDefaults_when_householdIsCreated() {
        Household household = householdRepository.saveAndFlush(Household.create("테스트 Household"));

        assertThat(household.getBaseCurrency()).isEqualTo("KRW");
        assertThat(household.getTimezone()).isEqualTo("Asia/Seoul");
    }

    @Test
    void should_rejectDuplicateMembership_when_sameUserIsInsertedTwice() {
        User user = userRepository.saveAndFlush(User.create("owner@example.test", "Owner"));
        Household household = householdRepository.saveAndFlush(Household.create("테스트 Household"));
        householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, user, HouseholdRole.OWNER));

        assertThatThrownBy(() -> householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, user, HouseholdRole.MEMBER)))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void should_rejectSecondOwner_when_databaseConstraintIsApplied() {
        User owner = userRepository.saveAndFlush(User.create("owner@example.test", "Owner"));
        User secondOwner = userRepository.saveAndFlush(User.create("second@example.test", "Second"));
        Household household = householdRepository.saveAndFlush(Household.create("테스트 Household"));
        householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, owner, HouseholdRole.OWNER));

        assertThatThrownBy(() -> householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, secondOwner, HouseholdRole.OWNER)))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void should_rejectSecondOwner_when_membershipServiceIsUsed() {
        User owner = userRepository.saveAndFlush(User.create("owner@example.test", "Owner"));
        User secondOwner = userRepository.saveAndFlush(User.create("second@example.test", "Second"));
        Household household = householdRepository.saveAndFlush(Household.create("테스트 Household"));
        householdMembershipService.addMember(household.getId(), owner.getId(), HouseholdRole.OWNER);

        assertThatThrownBy(() -> householdMembershipService.addMember(
                household.getId(), secondOwner.getId(), HouseholdRole.OWNER))
                .isInstanceOf(HouseholdMembershipConflictException.class)
                .hasMessageContaining("OWNER");
        assertThat(householdMemberRepository.countByHousehold_Id(household.getId())).isEqualTo(1);
    }

    @Test
    void should_rejectThirdMember_when_householdAlreadyHasTwoMembers() {
        User owner = userRepository.saveAndFlush(User.create("owner@example.test", "Owner"));
        User member = userRepository.saveAndFlush(User.create("member@example.test", "Member"));
        User third = userRepository.saveAndFlush(User.create("third@example.test", "Third"));
        Household household = householdRepository.saveAndFlush(Household.create("테스트 Household"));
        householdMembershipService.addMember(household.getId(), owner.getId(), HouseholdRole.OWNER);
        householdMembershipService.addMember(household.getId(), member.getId(), HouseholdRole.MEMBER);

        assertThatThrownBy(() -> householdMembershipService.addMember(
                household.getId(), third.getId(), HouseholdRole.MEMBER))
                .isInstanceOf(HouseholdMemberLimitExceededException.class);
        assertThat(householdMemberRepository.countByHousehold_Id(household.getId())).isEqualTo(2);
    }

    @Test
    void should_returnExistingIds_when_bootstrapIsRepeatedWithExactInput() {
        HouseholdBootstrapResult created = householdBootstrapService.provision(BOOTSTRAP_REQUEST);
        HouseholdBootstrapResult repeated = householdBootstrapService.provision(BOOTSTRAP_REQUEST);

        assertThat(created.created()).isTrue();
        assertThat(repeated.created()).isFalse();
        assertThat(repeated.householdId()).isEqualTo(created.householdId());
        assertThat(repeated.ownerUserId()).isEqualTo(created.ownerUserId());
        assertThat(repeated.memberUserId()).isEqualTo(created.memberUserId());
        assertThat(userRepository.count()).isEqualTo(2);
        assertThat(householdRepository.count()).isEqualTo(1);
        assertThat(householdMemberRepository.count()).isEqualTo(2);
    }

    @Test
    void should_failFastWithoutOverwrite_when_bootstrapFindsPartialData() {
        User existing = userRepository.saveAndFlush(User.create("owner@example.test", "Existing"));

        assertThatThrownBy(() -> householdBootstrapService.provision(BOOTSTRAP_REQUEST))
                .isInstanceOf(HouseholdBootstrapConflictException.class)
                .hasMessageContaining("부분 생성");
        assertThat(userRepository.findById(existing.getId()))
                .get()
                .extracting(User::getDisplayName)
                .isEqualTo("Existing");
        assertThat(householdRepository.count()).isZero();
    }

    @Test
    void should_failFast_when_bootstrapFindsUnexpectedMembershipRoles() {
        HouseholdBootstrapResult result = householdBootstrapService.provision(BOOTSTRAP_REQUEST);
        User owner = userRepository.findByEmail("owner@example.test").orElseThrow();
        User member = userRepository.findByEmail("member@example.test").orElseThrow();
        Household household = householdRepository.findById(result.householdId()).orElseThrow();
        householdMemberRepository.deleteAllInBatch();
        householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, owner, HouseholdRole.MEMBER));
        householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, member, HouseholdRole.OWNER));

        assertThatThrownBy(() -> householdBootstrapService.provision(BOOTSTRAP_REQUEST))
                .isInstanceOf(HouseholdBootstrapConflictException.class)
                .hasMessageContaining("membership");
        assertThat(householdMemberRepository.count()).isEqualTo(2);
    }

    @Test
    void should_notRegisterBootstrapRunner_when_bootstrapIsDisabledByDefault() {
        assertThat(applicationContext.containsBean("householdBootstrapRunner")).isFalse();
    }
}
