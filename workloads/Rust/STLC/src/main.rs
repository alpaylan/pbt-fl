use {
    crabcheck::quickcheck::quickcheck,
    stlc::{
        spec,
        spec::ExprOpt,
    },
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


use std::time::Duration;

fn main() {
    let args = std::env::args().collect::<Vec<_>>();
    if args.len() < 3 {
        eprintln!("Usage: {} <tool> <property>", args[0]);
        eprintln!("Available tools: quickcheck");
        eprintln!("Available properties: SinglePreserve, MultiPreserve");
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
        ("quickcheck", "SinglePreserve") => {
            qc.quicktest(spec::prop_single_preserve as fn(ExprOpt) -> Option<bool>)
        },
        ("crabcheck", "SinglePreserve") => {
            quickcheck(spec::prop_single_preserve as fn(ExprOpt) -> Option<bool>).to_qc_result()
        },
        ("quickcheck", "MultiPreserve") => {
            qc.quicktest(spec::prop_multi_preserve as fn(ExprOpt) -> Option<bool>)
        },
        ("crabcheck", "MultiPreserve") => {
            quickcheck(spec::prop_multi_preserve as fn(ExprOpt) -> Option<bool>).to_qc_result()
        },
        _ => {
            panic!("Unknown tool or property: {} {}", tool, property)
        },
    };


    result.print_status();
}
