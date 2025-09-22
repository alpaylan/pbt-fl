use {
    crabcheck::quickcheck::quickcheck,
    rbt::{
        implementation::Tree,
        spec,
    },
    std::time::Duration,
    tracing_subscriber::EnvFilter,
};


trait QuickCheckResultExt {
    fn to_qc_result(self) -> quickcheck::QuickCheckResult;
}

impl QuickCheckResultExt for crabcheck::quickcheck::RunResult {
    fn to_qc_result(self) -> quickcheck::QuickCheckResult {
        match self.status {
            crabcheck::quickcheck::ResultStatus::Finished => {
                quickcheck::QuickCheckResult {
                    n_tests_passed: self.passed,
                    n_tests_discarded: self.discarded,
                    status: quickcheck::ResultStatus::Finished,
                    total_time: Duration::default(),
                    generation_time: Duration::default(),
                    shrinking_time: Duration::default(),
                    execution_time: Duration::default(),
                }
            },
            crabcheck::quickcheck::ResultStatus::Failed { arguments } => {
                quickcheck::QuickCheckResult {
                    n_tests_passed: self.passed,
                    n_tests_discarded: self.discarded,
                    status: quickcheck::ResultStatus::Failed { arguments },
                    total_time: Duration::default(),
                    generation_time: Duration::default(),
                    shrinking_time: Duration::default(),
                    execution_time: Duration::default(),
                }
            },
            crabcheck::quickcheck::ResultStatus::GaveUp => {
                quickcheck::QuickCheckResult {
                    n_tests_passed: self.passed,
                    n_tests_discarded: self.discarded,
                    status: quickcheck::ResultStatus::GaveUp,
                    total_time: Duration::default(),
                    generation_time: Duration::default(),
                    shrinking_time: Duration::default(),
                    execution_time: Duration::default(),
                }
            },
            crabcheck::quickcheck::ResultStatus::TimedOut => {
                quickcheck::QuickCheckResult {
                    n_tests_passed: self.passed,
                    n_tests_discarded: self.discarded,
                    status: quickcheck::ResultStatus::TimedOut,
                    total_time: Duration::default(),
                    generation_time: Duration::default(),
                    shrinking_time: Duration::default(),
                    execution_time: Duration::default(),
                }
            },
            crabcheck::quickcheck::ResultStatus::Aborted { error } => {
                quickcheck::QuickCheckResult {
                    n_tests_passed: self.passed,
                    n_tests_discarded: self.discarded,
                    status: quickcheck::ResultStatus::Aborted { err: Some(error) },
                    total_time: Duration::default(),
                    generation_time: Duration::default(),
                    shrinking_time: Duration::default(),
                    execution_time: Duration::default(),
                }
            },
        }
    }
}

fn main() {
    let args = std::env::args().collect::<Vec<_>>();
    tracing_subscriber::fmt().with_env_filter(EnvFilter::from_default_env()).with_ansi(true).init();
    if args.len() < 3 {
        eprintln!("Usage: {} <tool> <property>", args[0]);
        eprintln!("Available tools: quickcheck");
        eprintln!(
            "For available properties, check https://github.com/alpaylan/etna-cli/blob/main/docs/workloads/rbt.md"
        );
        return;
    }
    let tool = args[1].as_str();
    let property = args[2].as_str();

    let num_tests = 200_000_000;
    let mut qc = quickcheck::QuickCheck::new()
        .tests(num_tests)
        .max_tests(num_tests * 2)
        .max_time(Duration::from_secs(60 * 60));

    let result = match (tool, property) {
        ("quickcheck", "InsertValid") => {
            qc.quicktest(spec::prop_insert_valid as fn(Tree, i32, i32) -> Option<bool>)
        },
        ("quickcheck", "DeleteValid") => {
            qc.quicktest(spec::prop_delete_valid as fn(Tree, i32) -> Option<bool>)
        },
        ("quickcheck", "InsertPost") => {
            qc.quicktest(spec::prop_insert_post as fn(Tree, i32, i32, i32) -> Option<bool>)
        },
        ("quickcheck", "DeletePost") => {
            qc.quicktest(spec::prop_delete_post as fn(Tree, i32, i32) -> Option<bool>)
        },
        ("quickcheck", "InsertModel") => {
            qc.quicktest(spec::prop_insert_model as fn(Tree, i32, i32) -> Option<bool>)
        },
        ("quickcheck", "DeleteModel") => {
            qc.quicktest(spec::prop_delete_model as fn(Tree, i32) -> Option<bool>)
        },
        ("quickcheck", "InsertInsert") => {
            qc.quicktest(spec::prop_insert_insert as fn(Tree, i32, i32, i32, i32) -> Option<bool>)
        },
        ("quickcheck", "InsertDelete") => {
            qc.quicktest(spec::prop_insert_delete as fn(Tree, i32, i32, i32) -> Option<bool>)
        },
        ("quickcheck", "DeleteInsert") => {
            qc.quicktest(spec::prop_delete_insert as fn(Tree, i32, i32, i32) -> Option<bool>)
        },
        ("quickcheck", "DeleteDelete") => {
            qc.quicktest(spec::prop_delete_delete as fn(Tree, i32, i32) -> Option<bool>)
        },
        ("crabcheck", "InsertValid") => {
            quickcheck(|(t, k, v)| spec::prop_insert_valid(t, k, v)).to_qc_result()
        },
        ("crabcheck", "DeleteValid") => {
            quickcheck(|(t, k)| spec::prop_delete_valid(t, k)).to_qc_result()
        },
        ("crabcheck", "InsertPost") => {
            quickcheck(|(t, k1, k2, v)| spec::prop_insert_post(t, k1, k2, v)).to_qc_result()
        },
        ("crabcheck", "DeletePost") => {
            quickcheck(|(t, k1, k2)| spec::prop_delete_post(t, k1, k2)).to_qc_result()
        },
        ("crabcheck", "InsertModel") => {
            quickcheck(|(t, k, v)| spec::prop_insert_model(t, k, v)).to_qc_result()
        },
        ("crabcheck", "DeleteModel") => {
            quickcheck(|(t, k)| spec::prop_delete_model(t, k)).to_qc_result()
        },
        ("crabcheck", "InsertInsert") => {
            quickcheck(|(t, k1, k2, v1, v2)| spec::prop_insert_insert(t, k1, k2, v1, v2))
                .to_qc_result()
        },
        ("crabcheck", "InsertDelete") => {
            quickcheck(|(t, k1, k2, v)| spec::prop_insert_delete(t, k1, k2, v)).to_qc_result()
        },
        ("crabcheck", "DeleteInsert") => {
            quickcheck(|(t, k1, k2, v)| spec::prop_delete_insert(t, k1, k2, v)).to_qc_result()
        },
        ("crabcheck", "DeleteDelete") => {
            quickcheck(|(t, k1, k2)| spec::prop_delete_delete(t, k1, k2)).to_qc_result()
        },
        _ => {
            panic!("Unknown tool or property: {} {}", tool, property)
        },
    };

    result.print_status();
}
